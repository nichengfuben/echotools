"""流式 fncall 检测状态机（协议感知版本）。

从 src/core/tools.py 迁移并改造为协议感知。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from echotools.protocol.base import ToolProtocol


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

        # Precompute end tags from trigger tags (avoids per-chunk string parsing)
        self._end_tags: List[str] = []
        for tag in protocol.get_trigger_tags():
            if tag.startswith("<") and not tag.startswith("</"):
                tag_name = tag.lstrip("<").split(">")[0].split()[0]
                self._end_tags.append(f"</{tag_name}>")
            elif tag.startswith("[") and not tag.startswith("[/"):
                inner = tag.lstrip("[").split("]")[0]
                self._end_tags.append(f"[/{inner}]")

    @staticmethod
    def _split_safe_text(
        buffer: str,
        tags: List[str],
    ) -> Tuple[str, str]:
        """将 buffer 分为「可安全输出的前缀」和「需保留的尾部」。"""
        if not buffer:
            return "", ""

        max_keep = max(len(t) - 1 for t in tags)
        check_len = min(len(buffer), max_keep)

        for length in range(check_len, 0, -1):
            suffix = buffer[-length:]
            if any(tag.startswith(suffix) and suffix != tag for tag in tags):
                return buffer[:-length], buffer[-length:]

        return buffer, ""

    def _feed_waiting(self, chunk: str) -> None:
        """在 WAITING_FOR_TAG 状态下处理新块。"""
        combined = self._waiting_tail + chunk
        found, pos = self._protocol.detect_start(combined)

        trigger_tags = self._protocol.get_trigger_tags()

        if not found:
            safe, remain = self._split_safe_text(combined, trigger_tags)
            if safe:
                self._text_parts.append(safe)
            self._waiting_tail = remain
            return

        if pos > 0:
            self._text_parts.append(combined[:pos])

        self._fncall_buf = combined[pos:]
        self._waiting_tail = ""
        self._detected = True
        self._state = self.IN_FUNCTION_CALLS

        # 检查是否已闭合（单块内完成）
        if self._is_call_closed():
            self._state = self.DONE

    def _is_call_closed(self) -> bool:
        """检测 fncall 缓冲区中是否包含结束标记。"""
        buf = self._fncall_buf
        for end_tag in self._end_tags:
            if end_tag in buf:
                return True
        # Fallback only for protocols without recognizable end tags
        if not self._end_tags:
            return "</" in buf or "]" in buf or "}" in buf
        return False

    def feed(self, chunk: str) -> None:
        """喂入新的流式文本块。DONE 或 finalize 后调用静默忽略。"""
        if not chunk or self._state == self.DONE:
            return
        if self._finalized_result is not None:
            return

        self._raw_buf += chunk

        if self._state == self.WAITING_FOR_TAG:
            self._feed_waiting(chunk)
        else:
            self._fncall_buf += chunk
            if self._is_call_closed():
                self._state = self.DONE

    def finalize(self) -> Tuple[str, List[Dict[str, Any]]]:
        """结束流式解析，返回 (清理后文本, tool_calls 列表)。幂等。"""
        if self._finalized_result is not None:
            return self._finalized_result

        self._state = self.DONE

        if not self._detected:
            full_text = "".join(self._text_parts) + self._waiting_tail
            result = self._protocol.parse(full_text, self._tools)
        else:
            clean_text = "".join(self._text_parts).strip()
            _, tool_calls = self._protocol.parse(self._fncall_buf, self._tools)
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
