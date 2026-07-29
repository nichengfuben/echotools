"""FncallStreamParser waiting/feed helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class StreamFeedMixin:
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

    def _hold_or_split_content(self, text: str, trigger_tags) -> bool:
        """True 表示已消费 text（含 holdback）。"""
        hold_from_fn = getattr(self._protocol, "find_fncall_hold_from", None)
        if hold_from_fn is not None:
            hold_from = hold_from_fn(text, tools=self._tools)
            if hold_from is not None:
                if hold_from > 0:
                    self._append_content_text(text[:hold_from])
                self._waiting_tail = text[hold_from:]
                return True
        safe, remain = self._split_safe_text(text, trigger_tags)
        if safe:
            self._append_content_text(safe)
        self._waiting_tail = remain
        return True

    def _hold_or_split_emit(self, text: str, trigger_tags) -> None:
        hold_from_fn = getattr(self._protocol, "find_fncall_hold_from", None)
        if hold_from_fn is not None:
            hold_from = hold_from_fn(text, tools=self._tools)
            if hold_from is not None:
                if hold_from > 0:
                    self._emit_text(text[:hold_from])
                self._waiting_tail = text[hold_from:]
                return
        safe, remain = self._split_safe_text(text, trigger_tags)
        if safe:
            self._emit_text(safe)
        self._waiting_tail = remain

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
            found, pos = self._protocol.detect_start(text, tools=self._tools)
            if found:
                if pos > 0:
                    self._append_content_text(text[:pos])
                self._fncall_buf += text[pos:]
                return
            self._hold_or_split_content(text, trigger_tags)
            return
        trigger_tags = self._protocol.get_trigger_tags()
        found, pos = self._protocol.detect_start(text, tools=self._tools)
        if not found:
            self._hold_or_split_content(text, trigger_tags)
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
        if self._thinking_filter is not None and self._thinking_filter.in_open_thinking():
            self._feed_waiting_thinking_plain(combined)
            return
        trigger_tags = self._protocol.get_trigger_tags()
        found, pos = self._protocol.detect_start(combined, tools=self._tools)
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
                self._emit_text(combined[:pos])
            self._begin_function_calls(combined, pos=pos)
            return
        # detect_start 之后再处理未闭合 thinking，避免 legacy 外壳后 `<en` 误 hold
        if self._thinking_filter is not None:
            from echotools.exec.fncall.protocols.entml_think.parse import (
                has_unclosed_entml_thinking,
            )
            if has_unclosed_entml_thinking(
                combined, thinking_enabled=self._thinking_enabled
            ):
                self._feed_waiting_thinking_plain(combined)
                return
        self._hold_or_split_emit(combined, trigger_tags)

