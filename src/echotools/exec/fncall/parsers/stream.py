"""流式 fncall 检测状态机（协议感知版本）。

从 src/core/tools.py 迁移并改造为协议感知。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from echotools.exec.protocol.base import ToolProtocol


# 懒导入：仅 entml 协议需要
def _make_thinking_filter(protocol: ToolProtocol, *, thinking_enabled: bool = True):
    if not thinking_enabled:
        return None
    if getattr(protocol, "id", None) == "entml":
        from echotools.exec.fncall.protocols.entml_think.parse import (
            EntmlThinkingStreamFilter,
        )
        return EntmlThinkingStreamFilter(thinking_enabled=thinking_enabled)
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
        protocol_options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._protocol = protocol
        self._tools = tools
        from echotools.exec.fncall.protocols.entml_think.core import is_thinking_enabled

        self._thinking_enabled = is_thinking_enabled(protocol_options)
        self._raw_buf: str = ""
        self._text_parts: List[str] = []
        self._waiting_tail: str = ""
        self._fncall_buf: str = ""
        self._detected: bool = False
        self._state: str = self.WAITING_FOR_TAG
        self._finalized_result: Optional[Tuple[str, List[Dict[str, Any]]]] = None
        self._thinking_parts: List[str] = []
        self._thinking_filter = _make_thinking_filter(
            protocol, thinking_enabled=self._thinking_enabled
        )
        self._emitted_invoke_count: int = 0
        self._json_stream_encoder = None
        self._pending_stream_deltas: Deque[Tuple[str, str, int]] = deque()
        self._stream_invoke_emitted: List[str] = []
        self._schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None

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

    def _get_schema_index(self) -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
        if self._schema_index is None and self._tools:
            from echotools.exec.fncall.shared.coercion import _build_param_schema_index

            self._schema_index = _build_param_schema_index(self._tools)
        return self._schema_index

    def _emit_text(self, text: str) -> None:
        """将文本路由给思考过滤器（若启用）或直接追加到 _text_parts。"""
        if not text:
            return
        if self._thinking_filter is not None:
            for kind, part in self._thinking_filter.feed(text):
                if kind == "thinking":
                    self._thinking_parts.append(part)
                else:
                    self._append_content_text(part)
        else:
            self._append_content_text(text)

    def _trim_trailing_visible_whitespace(self) -> None:
        """invoke 开始前去掉尾部空白可见段（thinking-only 回复常见 ``\\n\\n``）。"""
        while self._text_parts and not self._text_parts[-1].strip():
            self._text_parts.pop()
        if self._text_parts:
            trimmed = self._text_parts[-1].rstrip()
            if trimmed:
                self._text_parts[-1] = trimmed
            else:
                self._text_parts.pop()

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
        if not text:
            return
        from echotools.exec.fncall.protocols.entml_think.parse import (
            _THINKING_CLOSE,
            strip_orphan_thinking_close_prefix,
        )

        remainder = strip_orphan_thinking_close_prefix(text)
        while True:
            stripped = remainder.strip()
            if not stripped:
                return
            if stripped == _THINKING_CLOSE:
                return
            if _THINKING_CLOSE in remainder:
                before, _, after = remainder.partition(_THINKING_CLOSE)
                if before.strip():
                    self._text_parts.append(before)
                remainder = after
                continue
            self._text_parts.append(remainder)
            return

    def _normalize_stream_chunk(self, text: str) -> str:
        fn = getattr(self._protocol, "normalize_stream_buffer", None)
        if callable(fn):
            return fn(text)
        return text

    def _invoke_close_tag(self) -> str:
        return self._end_tags[0] if self._end_tags else "</entml:invoke>"

    def _drain_thinking_holdback_to_fncall(self) -> None:
        """invoke 已开始后，thinking 过滤器里对工具标签的 holdback 应并入 fncall 缓冲。"""
        if self._thinking_filter is None:
            return
        pending = self._thinking_filter._pending
        if pending:
            self._fncall_buf += pending
            self._thinking_filter._pending = ""

    def _begin_function_calls(self, buffer_from: str, *, pos: int) -> None:
        self._trim_trailing_visible_whitespace()
        self._fncall_buf = buffer_from[pos:]
        self._drain_thinking_holdback_to_fncall()
        self._detected = True
        self._state = self.IN_FUNCTION_CALLS
        self._json_stream_encoder = None
        if self._thinking_filter is not None:
            self._thinking_filter.clear_invoke_handoff_state()

    def _feed_content_waiting(self, text: str) -> None:
        """thinking 已闭合后，对可见正文做 invoke 检测（不再经过 thinking 过滤器）。"""
        if not text:
            return
        text = self._normalize_stream_chunk(text)
        if self._state == self.IN_FUNCTION_CALLS:
            close_tag = self._invoke_close_tag()
            if not self._is_call_closed():
                if close_tag in text:
                    idx = text.find(close_tag)
                    self._fncall_buf += text[: idx + len(close_tag)]
                    tail = text[idx + len(close_tag) :]
                    if tail:
                        self._feed_content_waiting(tail)
                    return
                self._fncall_buf += text
                return
            trigger_tags = self._protocol.get_trigger_tags()
            found, pos = self._protocol.detect_start(text)
            if found:
                if pos > 0:
                    self._append_content_text(text[:pos])
                self._fncall_buf += text[pos:]
                return
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

        from echotools.exec.fncall.protocols.entml_think.parse import (
            invoke_index_inside_any_thinking_block,
        )
        if invoke_index_inside_any_thinking_block(
            text, pos, thinking_enabled=self._thinking_enabled,
        ):
            self._append_content_text(text)
            return

        if pos > 0:
            self._append_content_text(text[:pos])

        self._begin_function_calls(text, pos=pos)

    def _feed_waiting_thinking_plain(self, combined: str) -> None:
        """未闭合 thinking 阶段：块内一律按纯文本进 thinking，不检测 invoke。"""
        assert self._thinking_filter is not None
        for kind, part in self._thinking_filter.feed(combined):
            if kind == "thinking":
                self._thinking_parts.append(part)
            elif part:
                self._feed_content_waiting(part)
        if self._state == self.IN_FUNCTION_CALLS:
            self._drain_thinking_holdback_to_fncall()

    def _feed_waiting(self, chunk: str) -> None:
        """在 WAITING_FOR_TAG / IN_FUNCTION_CALLS 状态下处理新块。"""
        combined = self._normalize_stream_chunk(self._waiting_tail + chunk)
        self._waiting_tail = ""

        if self._state == self.IN_FUNCTION_CALLS:
            if self._thinking_filter is not None and self._thinking_filter.in_open_thinking():
                self._feed_waiting_thinking_plain(combined)
                return
            if self._waiting_tail:
                self._fncall_buf += self._normalize_stream_chunk(self._waiting_tail)
                self._waiting_tail = ""
            self._drain_thinking_holdback_to_fncall()
            if not self._is_call_closed():
                self._fncall_buf += combined
                return
            self._feed_content_waiting(combined)
            return

        # 已进入 thinking 块时，块内不做 invoke 检测。
        if self._thinking_filter is not None and self._thinking_filter.in_open_thinking():
            self._feed_waiting_thinking_plain(combined)
            return

        trigger_tags = self._protocol.get_trigger_tags()
        found, pos = self._protocol.detect_start(combined)

        if found:
            if self._thinking_filter is not None:
                from echotools.exec.fncall.protocols.entml_think.parse import (
                    invoke_index_inside_any_thinking_block,
                )
                if invoke_index_inside_any_thinking_block(
                    combined, pos, thinking_enabled=self._thinking_enabled,
                ):
                    self._feed_waiting_thinking_plain(combined)
                    return
            if pos > 0:
                # 工具标签前的正文仍可能含 thinking，走过滤器。
                self._emit_text(combined[:pos])
            self._begin_function_calls(combined, pos=pos)
            return

        # 无完整工具开标签时，再处理未闭合 thinking / 思考开标签 holdback。
        # 必须放在 detect_start 之后：否则 legacy 外壳后的 `<en` 会被
        # 尾部误判为 thinking 前缀，导致 invoke 内容被截断。
        if self._thinking_filter is not None:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                has_unclosed_entml_thinking,
            )
            if has_unclosed_entml_thinking(
                combined, thinking_enabled=self._thinking_enabled
            ):
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

    def _stream_active_invoke_slot(self) -> int:
        """当前正在流式编码的 invoke 序号（0-based）。"""
        from echotools.exec.fncall.protocols.entml_patterns import INVOKE_RE
        from echotools.exec.fncall.protocols.entml_stream_json import (
            _INVOKE_CLOSE,
            _INVOKE_OPEN_PREFIX,
            split_invoke_open,
        )

        complete = list(INVOKE_RE.finditer(self._fncall_buf))
        complete_n = len(complete)
        parsed = split_invoke_open(self._fncall_buf)
        if parsed is None:
            return max(0, complete_n - 1)
        _name, body_start = parsed
        body = self._fncall_buf[body_start:]
        if _INVOKE_CLOSE in body:
            return max(0, complete_n - 1)
        open_pos = self._fncall_buf.rfind(_INVOKE_OPEN_PREFIX)
        if complete and open_pos >= complete[-1].end():
            return complete_n
        return max(0, complete_n - 1)

    def _merge_or_append_pending_delta(self, name: str, piece: str, slot: int) -> None:
        if not piece:
            return
        if self._pending_stream_deltas and self._pending_stream_deltas[-1][2] == slot:
            prev_name, prev_piece, prev_slot = self._pending_stream_deltas[-1]
            self._pending_stream_deltas[-1] = (prev_name, prev_piece + piece, prev_slot)
        else:
            self._pending_stream_deltas.append((name, piece, slot))

    def _pending_body_for_name(self, name: str) -> str:
        return "".join(p for n, p in self._pending_stream_deltas if n == name)

    def _track_stream_delta(self, name: str, piece: str) -> None:
        slot = self._stream_active_invoke_slot()
        while len(self._stream_invoke_emitted) <= slot:
            self._stream_invoke_emitted.append("")
        self._stream_invoke_emitted[slot] += piece
        self._merge_or_append_pending_delta(name, piece, slot)

    def _ensure_ready_invoke_stream_tails(
        self, ready: List[Dict[str, Any]]
    ) -> None:
        """invoke ready 时补齐 partial_json 尾部，避免大 chunk 下缺 ``}``。"""
        if not ready:
            return
        base = self._emitted_invoke_count - len(ready)
        multi = len(ready) > 1
        if multi:
            self._pending_stream_deltas.clear()
        for offset, call in enumerate(ready):
            idx = base + offset
            while len(self._stream_invoke_emitted) <= idx:
                self._stream_invoke_emitted.append("")
            final = call["function"]["arguments"]
            prev = self._stream_invoke_emitted[idx]
            if final.startswith(prev):
                tail = final[len(prev) :]
            elif not prev:
                pname = call["function"]["name"]
                pending_body = self._pending_body_for_name(pname) if not multi else ""
                if final.startswith(pending_body):
                    tail = final[len(pending_body) :]
                elif not pending_body:
                    tail = final
                else:
                    tail = ""
            else:
                tail = ""
            if tail:
                name = call["function"]["name"]
                if multi:
                    self._pending_stream_deltas.append((name, tail, idx))
                else:
                    self._merge_or_append_pending_delta(name, tail, idx)
            self._stream_invoke_emitted[idx] = final
        if self._json_stream_encoder is not None:
            from echotools.exec.fncall.protocols.entml_stream_json import (
                _INVOKE_CLOSE,
                build_streaming_json_snapshot,
                split_invoke_open,
            )

            parsed = split_invoke_open(self._fncall_buf)
            if parsed:
                name, body_start = parsed
                body = self._fncall_buf[body_start:]

                if _INVOKE_CLOSE not in body:
                    snap = build_streaming_json_snapshot(
                        body,
                        tool_name=name,
                        schema_index=self._get_schema_index(),
                    )
                    self._json_stream_encoder.set_tool_context(
                        name, self._get_schema_index()
                    )
                    self._json_stream_encoder._emitted = snap
                else:
                    self._json_stream_encoder.reset()
            else:
                self._json_stream_encoder.reset()

    def _sync_json_stream_encoder_emitted(self) -> None:
        """invoke 已 ready 后对齐 encoder，避免下一 chunk 重发整段 partial_json。"""
        if self._json_stream_encoder is None:
            return
        from echotools.exec.fncall.protocols.entml_stream_json import (
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            self._json_stream_encoder.reset()
            return
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        self._json_stream_encoder.poll(body)

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

        if self._state != self.DONE:
            self._feed_waiting(chunk)

        polled = self._poll_streaming_tool_input_delta()
        if polled:
            self._track_stream_delta(polled[0], polled[1])
        ready = self.get_ready_tool_calls()
        if ready:
            self._ensure_ready_invoke_stream_tails(ready)
        return ready

    def _poll_streaming_tool_input_delta(self) -> Optional[Tuple[str, str]]:
        """invoke 开标签完整匹配后，返回 (tool_name, partial_json_delta)。"""
        if not self._detected or getattr(self._protocol, "id", None) != "entml":
            return None
        if self._state not in (self.IN_FUNCTION_CALLS,):
            return None
        from echotools.exec.fncall.protocols.entml_patterns import INVOKE_RE
        from echotools.exec.fncall.protocols.entml_stream_json import (
            _INVOKE_CLOSE,
            EntmlInvokeJsonStreamEncoder,
            build_streaming_json_snapshot,
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            return None
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        complete = list(INVOKE_RE.finditer(self._fncall_buf))
        complete_n = len(complete)
        if _INVOKE_CLOSE in body:
            if complete_n <= self._emitted_invoke_count:
                return None
            # 同一 chunk 内多个 invoke 同时闭合时，由 ensure 按序入队，避免只 poll 最后一个
            if complete_n - self._emitted_invoke_count > 1:
                return None
            slot = max(0, complete_n - 1)
            schema_index = self._get_schema_index()
            final = build_streaming_json_snapshot(
                body,
                tool_name=name,
                schema_index=schema_index,
            )
            while len(self._stream_invoke_emitted) <= slot:
                self._stream_invoke_emitted.append("")
            if self._stream_invoke_emitted[slot] == final:
                return None
        schema_index = self._get_schema_index()
        if self._json_stream_encoder is None:
            self._json_stream_encoder = EntmlInvokeJsonStreamEncoder(
                tool_name=name,
                schema_index=schema_index,
            )
        else:
            self._json_stream_encoder.set_tool_context(name, schema_index)
        delta = self._json_stream_encoder.poll(body)
        if not delta:
            return None
        return (name, delta)

    def consume_stream_delta(self) -> Optional[Tuple[str, str]]:
        """取出本轮 ``feed`` 产生的 streaming partial_json 增量（FIFO，可多段）。"""
        if not self._pending_stream_deltas:
            return None
        name, piece, _slot = self._pending_stream_deltas.popleft()
        return (name, piece)

    def stream_invoke_argument_snapshots(self) -> List[str]:
        """各 invoke slot 已流式发出的 arguments JSON 累积（与 batch 对齐）。"""
        return list(self._stream_invoke_emitted)

    @property
    def streaming_invoke_closed(self) -> bool:
        """流式 fncall 缓冲中是否已出现 ``</entml:invoke>``。"""
        if getattr(self._protocol, "id", None) != "entml":
            return False
        from echotools.exec.fncall.protocols.entml_stream_json import _INVOKE_CLOSE

        return _INVOKE_CLOSE in self._fncall_buf

    def complete_stream_delta_if_needed(self) -> Optional[Tuple[str, str]]:
        """invoke 已开标签但未闭合时，补齐 partial_json 尾部的合法 JSON 后缀。"""
        if not self._detected or getattr(self._protocol, "id", None) != "entml":
            return None
        if self.streaming_invoke_closed:
            return None
        from echotools.exec.fncall.protocols.entml_stream_json import (
            EntmlInvokeJsonStreamEncoder,
            build_streaming_json_snapshot,
            split_invoke_open,
        )

        parsed = split_invoke_open(self._fncall_buf)
        if not parsed:
            return None
        name, body_start = parsed
        body = self._fncall_buf[body_start:]
        schema_index = self._get_schema_index()
        snapshot = build_streaming_json_snapshot(
            body,
            tool_name=name,
            schema_index=schema_index,
            force_close=True,
        )
        if not snapshot:
            return None
        if self._json_stream_encoder is None:
            self._json_stream_encoder = EntmlInvokeJsonStreamEncoder(
                tool_name=name,
                schema_index=schema_index,
            )
        else:
            self._json_stream_encoder.set_tool_context(name, schema_index)
        delta = self._json_stream_encoder.poll(body, force_close=True)
        if not delta:
            return None
        return (name, delta)

    def _assembly_for_tool_parse(self) -> str:
        """可供工具解析的已缓冲文本（不含 thinking 过滤器内部 pending）。"""
        return "".join(self._text_parts) + self._waiting_tail + self._fncall_buf

    def _stream_visible_buffer(self) -> str:
        """与 batch ``parse`` 一致：未闭合 thinking 之后的正文不参与可见/剥离。"""
        from echotools.exec.fncall.protocols.entml_think.parse import (
            clean_stream_partial_visible,
            stream_safe_visible_prefix,
        )

        from echotools.exec.fncall.protocols.entml_think.parse import (
            split_entml_thinking,
        )

        buf = stream_safe_visible_prefix(
            self._raw_buf,
            thinking_enabled=self._thinking_enabled,
        )
        if self._thinking_enabled and buf:
            buf, _ = split_entml_thinking(buf, thinking_enabled=True)
        return clean_stream_partial_visible(
            buf,
            has_calls=self.has_calls,
            thinking_enabled=self._thinking_enabled,
        )

    def _stream_display_text(self) -> str:
        """流式可见正文：在完整 raw 缓冲上剥离伪 history（保留 thinking 保护区）。"""
        from echotools.exec.fncall.shared.history_markup import (
            strip_fake_history_markup_for_display,
        )
        from echotools.exec.fncall.protocols.entml_think.parse import (
            split_entml_thinking,
        )

        buf = self._stream_visible_buffer()
        if not buf:
            return ""
        cleaned, _ = strip_fake_history_markup_for_display(buf)
        visible, _ = split_entml_thinking(
            cleaned, thinking_enabled=self._thinking_enabled
        )
        return visible

    def _stream_partial_display_text(self) -> str:
        """流式 ``partial_text``：在 invoke 起点前截断 raw，保留尾部 holdback 空白。"""
        from echotools.exec.fncall.shared.history_markup import (
            strip_fake_history_markup_for_display,
        )
        from echotools.exec.fncall.protocols.entml_think.parse import (
            clean_stream_partial_visible,
            split_entml_thinking,
            stream_safe_visible_prefix,
        )

        raw = self._raw_buf
        if not raw:
            return ""

        lower = raw.lower()
        cut = len(raw)
        for marker in ("<entml:invoke", "<entml:function_calls"):
            pos = lower.find(marker)
            if pos >= 0:
                cut = min(cut, pos)
        segment = raw[:cut]

        buf = stream_safe_visible_prefix(
            segment,
            thinking_enabled=self._thinking_enabled,
        )
        if not buf:
            return ""
        cleaned, _ = strip_fake_history_markup_for_display(buf)
        visible, _ = split_entml_thinking(
            cleaned,
            thinking_enabled=self._thinking_enabled,
            preserve_visible_whitespace=True,
        )
        return clean_stream_partial_visible(
            visible,
            has_calls=self.has_calls,
            thinking_enabled=self._thinking_enabled,
        )

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
                    self._append_content_text(part)

        # 与 batch parse 同路径（须在含 thinking 标签的 raw 缓冲上剥离伪 history）。
        clean_text, tool_calls = self._protocol.parse(
            self._raw_buf,
            self._tools,
            thinking_enabled=self._thinking_enabled,
        )

        clean_fn = getattr(self._protocol, "clean_tool_tags", None)
        if callable(clean_fn):
            clean_text = clean_fn(clean_text)
        elif getattr(self._protocol, "id", None) == "entml":
            from echotools.exec.fncall.protocols.entml_patterns import (
                strip_tool_entml_residue,
            )
            clean_text = strip_tool_entml_residue(clean_text)

        if self._thinking_enabled:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                split_entml_thinking,
            )

            display_text, _ = split_entml_thinking(
                clean_text, thinking_enabled=self._thinking_enabled
            )
        else:
            display_text = clean_text
        self._text_parts = [display_text] if display_text else []
        result = (display_text, tool_calls)

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
        if self._finalized_result is not None:
            clean_text, _ = self._finalized_result
            return clean_text

        from echotools.exec.fncall.protocols.entml_think.parse import (
            clean_stream_partial_visible,
        )

        if self._thinking_enabled and self._raw_buf:
            return clean_stream_partial_visible(
                self._stream_partial_display_text(),
                has_calls=self.has_calls,
                thinking_enabled=self._thinking_enabled,
            )

        text = clean_stream_partial_visible(
            self._normalize_stream_chunk("".join(self._text_parts)),
            has_calls=self.has_calls,
            thinking_enabled=self._thinking_enabled,
        )
        if text:
            from echotools.exec.fncall.shared.history_markup import (
                strip_fake_history_markup_for_display,
            )

            cleaned, _ = strip_fake_history_markup_for_display(text)
            cleaned = clean_stream_partial_visible(
                cleaned,
                has_calls=self.has_calls,
                thinking_enabled=self._thinking_enabled,
            )
            if cleaned:
                return cleaned
        return ""

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
                parse_kwargs: Dict[str, Any] = {}
                if getattr(self._protocol, "id", None) == "entml":
                    parse_kwargs["include_tool_blocks"] = False
                    parse_kwargs["thinking_enabled"] = self._thinking_enabled
                _, all_calls = self._protocol.parse(
                    self._raw_buf, self._tools, **parse_kwargs
                )
            except Exception:
                return []
        if len(all_calls) <= self._emitted_invoke_count:
            return []
        new_calls = all_calls[self._emitted_invoke_count :]
        self._emitted_invoke_count = len(all_calls)
        return new_calls
