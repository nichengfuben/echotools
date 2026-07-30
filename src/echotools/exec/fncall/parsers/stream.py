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


from echotools.exec.fncall.parsers.stream_delta import StreamDeltaMixin
from echotools.exec.fncall.parsers.stream_feed import StreamFeedMixin
from echotools.exec.fncall.parsers.stream_final import StreamFinalMixin


class FncallStreamParser(StreamFeedMixin, StreamDeltaMixin, StreamFinalMixin):
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

    def _init_end_tags(self, protocol: ToolProtocol) -> None:
        # 1 声明非空结束标记 / 2 声明空列表禁自动关闭 / 3 从 trigger 推断
        self._end_tags: List[str] = []
        self._no_auto_close: bool = False
        if hasattr(protocol, "get_stream_end_tags"):
            declared = list(protocol.get_stream_end_tags())
            if declared:
                self._end_tags = declared
            else:
                self._no_auto_close = True
            return
        for tag in protocol.get_trigger_tags():
            if tag.startswith("<") and not tag.startswith("</"):
                tag_name = tag.lstrip("<").split(">")[0].split()[0]
                end = f"</{tag_name}>"
                if end != tag.replace("<", "</"):
                    self._end_tags.append(end)
            elif tag.startswith("[") and not tag.startswith("[/"):
                inner = tag.lstrip("[").split("]")[0]
                self._end_tags.append(f"[/{inner}]")

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
        self._init_end_tags(protocol)

    def _get_schema_index(self) -> Optional[Dict[str, Dict[str, Dict[str, Any]]]]:
        if self._schema_index is None and self._tools:
            from echotools.exec.fncall.shared.coercion import _build_param_schema_index

            self._schema_index = _build_param_schema_index(self._tools)
        return self._schema_index

    def _get_known_tool_names(self):
        from echotools.exec.fncall.protocols.entml_patterns import (
            resolve_known_tool_names,
        )

        return resolve_known_tool_names(self._tools, self._get_schema_index())

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

