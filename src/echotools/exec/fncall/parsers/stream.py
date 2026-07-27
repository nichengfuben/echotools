"""流式 fncall 检测状态机（协议感知版本）。

从 src/core/tools.py 迁移并改造为协议感知。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.protocol.base import ToolProtocol


# 懒导入：仅 entml 协议需要
def _make_thinking_filter(protocol: ToolProtocol):
    if getattr(protocol, "id", None) == "entml":
        from echotools.exec.fncall.protocols.entml_think.parse import (
            EntmlThinkingStreamFilter,
        )
        return EntmlThinkingStreamFilter()
    return None


class FncallStreamParser:
    """协议感知的流式 fncall 检测与解析状态机。

    用法::

        protocol = get_protocol("xml")
        parser = FncallStreamParser(protocol=protocol, tools=tools)
        parser.feed(chunk)
        clean_text, tool_calls = parser.finalize()
    """

    WAITING_FOR_TAG = "WAITING_FOR_TAG"
    IN_FUNCTION_CALLS = "IN_FUNCTION_CALLS"
    DONE = "DONE"

    def __init__(
        self,
        protocol: ToolProtocol,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._protocol = protocol
        self._tools = tools
        self._raw_buf: str = ""
        self._text_parts: List[str] = []
        self._waiting_tail: str = ""
        self._fncall_buf: str = ""
        self._detected: bool = False
        self._state: str = self.WAITING_FOR_TAG
        self._finalized_result: Optional[Tuple[str, List[Dict[str, Any]]]] = None
        self._thinking_parts: List[str] = []
        self._thinking_filter = _make_thinking_filter(protocol)
        self._emitted_invoke_count: int = 0

        # 三种情况：
        #   1. 协议实现了 get_stream_end_tags() 且返回非空列表  → 用声明的结束标记
        #   2. 协议实现了 get_stream_end_tags() 且返回空列表   → 禁止自动关闭，等 finalize()
        #   3. 协议未实现 get_stream_end_tags()               → 从 trigger tags 推断（旧协议兼容）
        self._end_tags: List[str] = []
        self._no_auto_close: bool = False
        if hasattr(protocol, "get_stream_end_tags"):
            declared = list(protocol.get_stream_end_tags())
            if declared:
                self._end_tags = declared
            else:
                self._no_auto_close = True
            return
        # 旧协议兼容：从 trigger tags 推断结束标记
        for tag in protocol.get_trigger_tags():
            if tag.startswith("<") and not tag.startswith("</"):
                tag_name = tag.lstrip("<").split(">")[0].split()[0]
                end = f"</{tag_name}>"
                if end != tag.replace("<", "</"):
                    self._end_tags.append(end)
            elif tag.startswith("[") and not tag.startswith("[/"):
                inner = tag.lstrip("[").split("]")[0]
                self._end_tags.append(f"[/{inner}]")

    def _emit_text(self, text: str) -> None:
        """将文本路由给思考过滤器（若启用）或直接追加到 _text_parts。"""
        if not text:
            return
        if self._thinking_filter is not None:
            for kind, part in self._thinking_filter.feed(text):
                if kind == "thinking":
                    self._thinking_parts.append(part)
                else:
                    self._text_parts.append(part)
        else:
            self._text_parts.append(text)

    @staticmethod
    def _split_safe_text(
        buffer: str,
        tags: List[str],
    ) -> Tuple[str, str]:
        """将 buffer 分为「可安全输出的前缀」和「需保留的尾部」。

        除了「尾部是 trigger 的真前缀」外，还处理：
        - trigger 已完整出现但尚未见到闭合 ``>``（例如 ``<entml:invoke name="x"``）
        - trigger 声明带 ``>`` 时，其去尾 ``>`` 形式同样参与 holdback
        """
        if not buffer:
            return "", ""
        if not tags:
            return buffer, ""

        bases: List[str] = []
        for tag in tags:
            if not tag:
                continue
            bases.append(tag)
            if tag.endswith(">") and len(tag) > 1:
                bases.append(tag[:-1])

        # 已匹配完整 base 但属性/闭合 ``>`` 尚未到齐：从 base 起点整体 hold
        hold_from: Optional[int] = None
        for base in bases:
            pos = buffer.find(base)
            if pos < 0:
                continue
            if ">" not in buffer[pos:]:
                if hold_from is None or pos < hold_from:
                    hold_from = pos
        if hold_from is not None:
            return buffer[:hold_from], buffer[hold_from:]

        max_keep = max(len(t) - 1 for t in bases)
        check_len = min(len(buffer), max_keep)

        for length in range(check_len, 0, -1):
            suffix = buffer[-length:]
            if any(tag.startswith(suffix) and suffix != tag for tag in bases):
                return buffer[:-length], buffer[-length:]

        return buffer, ""

    def _append_content_text(self, text: str) -> None:
        if text:
            self._text_parts.append(text)

    def _normalize_stream_chunk(self, text: str) -> str:
        fn = getattr(self._protocol, "normalize_stream_buffer", None)
        if callable(fn):
            return fn(text)
        return text

    def _feed_content_waiting(self, text: str) -> None:
        """thinking 已闭合后，对可见正文做 invoke 检测（不再经过 thinking 过滤器）。"""
        if not text:
            return
        text = self._normalize_stream_chunk(text)
        trigger_tags = self._protocol.get_trigger_tags()
        found, pos = self._protocol.detect_start(text)
        if not found:
            hold_from_fn = getattr(self._protocol, "find_fncall_hold_from", None)
            if hold_from_fn is not None:
                hold_from = hold_from_fn(text)
                if hold_from is not None:
                    if hold_from > 0:
                        self._append_content_text(text[:hold_from])
                    self._waiting_tail = text[hold_from:]
                    return
            safe, remain = self._split_safe_text(text, trigger_tags)
            if safe:
                self._append_content_text(safe)
            self._waiting_tail = remain
            return

        if pos > 0:
            self._append_content_text(text[:pos])

        self._fncall_buf = text[pos:]
        self._detected = True
        self._state = self.IN_FUNCTION_CALLS
        if self._is_call_closed():
            self._state = self.DONE

    def _feed_waiting_thinking_plain(self, combined: str) -> None:
        """未闭合 thinking 阶段：块内一律按纯文本进 thinking，不检测 invoke。"""
        assert self._thinking_filter is not None
        for kind, part in self._thinking_filter.feed(combined):
            if kind == "thinking":
                self._thinking_parts.append(part)
            elif part:
                self._feed_content_waiting(part)

    def _feed_waiting(self, chunk: str) -> None:
        """在 WAITING_FOR_TAG 状态下处理新块。"""
        combined = self._normalize_stream_chunk(self._waiting_tail + chunk)
        self._waiting_tail = ""

        # 已进入 thinking 块时，块内不做 invoke 检测。
        if self._thinking_filter is not None and self._thinking_filter.in_open_thinking():
            self._feed_waiting_thinking_plain(combined)
            return

        trigger_tags = self._protocol.get_trigger_tags()
        found, pos = self._protocol.detect_start(combined)

        if found:
            if pos > 0:
                # 工具标签前的正文仍可能含 thinking，走过滤器。
                self._emit_text(combined[:pos])
            self._fncall_buf = combined[pos:]
            self._detected = True
            self._state = self.IN_FUNCTION_CALLS
            if self._is_call_closed():
                self._state = self.DONE
            return

        # 无完整工具开标签时，再处理未闭合 thinking / 思考开标签 holdback。
        # 必须放在 detect_start 之后：否则 legacy 外壳后的 `<en` 会被
        # 尾部误判为 thinking 前缀，导致 invoke 内容被截断。
        if self._thinking_filter is not None:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                has_unclosed_entml_thinking,
            )
            if has_unclosed_entml_thinking(combined):
                self._feed_waiting_thinking_plain(combined)
                return

        hold_from_fn = getattr(self._protocol, "find_fncall_hold_from", None)
        if hold_from_fn is not None:
            hold_from = hold_from_fn(combined)
            if hold_from is not None:
                if hold_from > 0:
                    self._emit_text(combined[:hold_from])
                self._waiting_tail = combined[hold_from:]
                return

        safe, remain = self._split_safe_text(combined, trigger_tags)
        if safe:
            self._emit_text(safe)
        self._waiting_tail = remain

    def _is_call_closed(self) -> bool:
        """检测 fncall 缓冲区中是否包含结束标记。"""
        if self._no_auto_close:
            return False
        buf = self._fncall_buf
        for end_tag in self._end_tags:
            if end_tag in buf:
                return True
        return False

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """喂入新的流式文本块。

        返回本轮新完成的 tool_calls（与 ``get_ready_tool_calls()`` 相同语义：
        调用后计数前进，勿再对本轮结果重复调用 ``get_ready_tool_calls``）。
        DONE 或 finalize 后调用返回 ``[]``。
        """
        if not chunk or self._state == self.DONE:
            return []
        if self._finalized_result is not None:
            return []

        self._raw_buf += chunk

        if self._state == self.WAITING_FOR_TAG:
            self._feed_waiting(chunk)
        else:
            self._fncall_buf += self._normalize_stream_chunk(chunk)
            if self._is_call_closed():
                self._state = self.DONE

        return self.get_ready_tool_calls()

    def _assembly_for_tool_parse(self) -> str:
        """可供工具解析的已缓冲文本（不含 thinking 过滤器内部 pending）。"""
        return "".join(self._text_parts) + self._waiting_tail + self._fncall_buf

    def finalize(self) -> Tuple[str, List[Dict[str, Any]]]:
        """结束流式解析，返回 (清理后文本, tool_calls 列表)。幂等。"""
        if self._finalized_result is not None:
            return self._finalized_result

        self._state = self.DONE

        # 先把 holdback 尾部送入思考过滤器，再 finalize 过滤器
        if self._waiting_tail:
            self._emit_text(self._waiting_tail)
            self._waiting_tail = ""

        if self._thinking_filter is not None:
            for kind, part in self._thinking_filter.finalize():
                if kind == "thinking":
                    self._thinking_parts.append(part)
                else:
                    self._text_parts.append(part)

        # 统一从「可见正文 + fncall 缓冲」解析，避免漏检；thinking 已在过滤器中剥离
        assembled = "".join(self._text_parts) + self._fncall_buf
        clean_text, tool_calls = self._protocol.parse(assembled, self._tools)

        clean_fn = getattr(self._protocol, "clean_tool_tags", None)
        if callable(clean_fn):
            clean_text = clean_fn(clean_text)
        elif getattr(self._protocol, "id", None) == "entml":
            from echotools.exec.fncall.protocols.entml_patterns import (
                strip_tool_entml_residue,
            )
            clean_text = strip_tool_entml_residue(clean_text)

        # 兜底：剥离残留 <entml:thinking>（holdback 边界/分片异常时）
        if self._thinking_filter is not None and clean_text:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                split_entml_thinking,
            )
            clean_text, more_thinking = split_entml_thinking(clean_text)
            if more_thinking:
                self._thinking_parts.append(more_thinking)

        self._text_parts = [clean_text] if clean_text else []
        result = (clean_text, tool_calls)

        self._finalized_result = result
        return result

    @property
    def state(self) -> str:
        """当前状态：WAITING_FOR_TAG / IN_FUNCTION_CALLS / DONE。"""
        return self._state

    @property
    def has_calls(self) -> bool:
        """是否已检测到 fncall 触发标记。"""
        return self._detected

    @property
    def partial_text(self) -> str:
        """已确认的非 fncall 文本片段（可用于流式 UI 实时展示）。"""
        return "".join(self._text_parts)

    @property
    def partial_thinking(self) -> str:
        """已提取的 <entml:thinking> 思考链内容（累积，不含标签）。"""
        return "".join(self._thinking_parts)

    def get_ready_tool_calls(self) -> List[Dict[str, Any]]:
        """返回新完成的 tool_calls（增量，每次调用只返回上次调用之后新增的）。

        流式阶段可在每次 ``feed`` 后调用，无需等待整个 buffer 结束。
        """
        if self._finalized_result is not None:
            _, all_calls = self._finalized_result
        else:
            try:
                _, all_calls = self._protocol.parse(
                    self._assembly_for_tool_parse(),
                    self._tools,
                )
            except Exception:
                return []
        if len(all_calls) <= self._emitted_invoke_count:
            return []
        new_calls = all_calls[self._emitted_invoke_count :]
        self._emitted_invoke_count = len(all_calls)
        return new_calls
