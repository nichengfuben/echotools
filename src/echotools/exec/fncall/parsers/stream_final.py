"""FncallStreamParser finalize / partial display helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class StreamFinalMixin:
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

    def _finalize_display_text(self, clean_text: str) -> str:
        if not self._thinking_enabled:
            return clean_text
        from echotools.exec.fncall.protocols.entml_think.parse import (
            split_entml_thinking,
        )
        _, batch_thinking = split_entml_thinking(
            self._raw_buf, thinking_enabled=self._thinking_enabled
        )
        if batch_thinking:
            self._thinking_parts = [batch_thinking]
        display_text, _ = split_entml_thinking(
            clean_text, thinking_enabled=self._thinking_enabled
        )
        return display_text

    def finalize(self) -> Tuple[str, List[Dict[str, Any]]]:
        """结束流式解析，返回 (清理后文本, tool_calls 列表)。幂等。"""
        if self._finalized_result is not None:
            return self._finalized_result
        self._state = self.DONE
        if self._waiting_tail:
            self._emit_text(self._waiting_tail)
            self._waiting_tail = ""
        if self._thinking_filter is not None:
            for kind, part in self._thinking_filter.finalize():
                if kind == "thinking":
                    self._thinking_parts.append(part)
                else:
                    self._append_content_text(part)
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
        display_text = self._finalize_display_text(clean_text)
        self._text_parts = [display_text] if display_text else []
        self._finalized_result = (display_text, tool_calls)
        return self._finalized_result

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
