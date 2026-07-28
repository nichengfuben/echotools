from __future__ import annotations

import re
from typing import List, Optional, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_may_be_streaming,
    extract_attr_value,
    normalize_entml_name,
)

THINKING_BLOCK_RE = re.compile(
    r"<entml:thinking\b[^>]*>([\s\S]*?)</entml:thinking>",
    re.DOTALL,
)

_THINKING_OPEN_PREFIX = "<entml:thinking"
_PLAIN_THINKING_OPEN_PREFIX = "<thinking"
_THINKING_CLOSE = "</entml:thinking>"
_FAULT_THINKING_CLOSE = "</thinking>"
_ORPHAN_CLOSE_PREFIXES = (
    "</entml:thinking",
    "</thinking",
)
# 与 thinking 共享 `<entml:` 前缀的其它标签：歧义 holdback 应交由工具流式状态机处理
_AMBIGUOUS_ENTML_PREFIXES = (
    "<entml:invoke",
    "<entml:function_calls",
    "<entml:parameter",
    "<entml:parameters",
)
_INVOKE_PREFIX = "<entml:invoke"
_FUNCTION_CALLS_PREFIX = "<entml:function_calls"
_LEADING_HOLD_PREFIXES = _AMBIGUOUS_ENTML_PREFIXES + _ORPHAN_CLOSE_PREFIXES + (
    _THINKING_OPEN_PREFIX,
    _FUNCTION_CALLS_PREFIX,
    "<tool",
    "<assistant",
)


def leading_entml_tag_holdback_len(
    text: str,
    *,
    thinking_enabled: bool = True,
) -> int:
    """buffer 开头是 entml/thinking/invoke 标签真前缀时，应 hold 的字节数。"""
    if not text:
        return 0
    prefixes: List[str] = list(_LEADING_HOLD_PREFIXES)
    if thinking_enabled:
        prefixes.append(_PLAIN_THINKING_OPEN_PREFIX)
    for prefix in prefixes:
        if text.startswith(prefix):
            return 0
    max_hold = max(len(prefix) - 1 for prefix in prefixes)
    for length in range(min(len(text), max_hold), 0, -1):
        head = text[:length]
        if any(prefix.startswith(head) and head != prefix for prefix in prefixes):
            return length
    return 0


def stream_safe_visible_prefix(
    text: str,
    *,
    thinking_enabled: bool = True,
) -> str:
    """流式 UI 可安全展示的 prefix（不含未收齐的 entml/thinking 开标签）。"""
    if not text:
        return ""
    hold = leading_entml_tag_holdback_len(text, thinking_enabled=thinking_enabled)
    if hold >= len(text):
        return ""
    buf = text[hold:]
    if has_unclosed_entml_thinking(buf, thinking_enabled=thinking_enabled):
        open_at, _ = _find_earliest_thinking_open(
            buf, thinking_enabled=thinking_enabled
        )
        if open_at >= 0:
            return buf[:open_at]
    return buf


def trailing_entml_tag_holdback_len(text: str) -> int:
    """buffer 尾部是 entml/thinking 标签真前缀时，应 hold 的字节数。"""
    if not text:
        return 0
    lt = text.rfind("<")
    if lt < 0:
        return 0
    tail = text[lt:]
    candidates: List[str] = list(_LEADING_HOLD_PREFIXES) + [
        _THINKING_CLOSE,
        _FAULT_THINKING_CLOSE,
    ]
    for tag in candidates:
        if tag.startswith(tail) and tail != tag:
            return len(tail)
    return 0


def clean_stream_partial_visible(
    text: str,
    *,
    has_calls: bool = False,
    thinking_enabled: bool = True,
) -> str:
    """流式 ``partial_text``：去掉 orphan thinking 闭标签与未收齐 entml 前缀/后缀。"""
    if not text:
        return ""
    text = strip_orphan_thinking_close_prefix(text)
    hold_head = leading_entml_tag_holdback_len(
        text, thinking_enabled=thinking_enabled
    )
    if hold_head >= len(text):
        return ""
    text = text[hold_head:]
    tail_hold = trailing_entml_tag_holdback_len(text)
    if tail_hold:
        text = text[:-tail_hold]
    if has_calls:
        text = text.rstrip()
    if not text.strip():
        return ""
    if re.search(r"</?entml:", text, re.IGNORECASE):
        text = re.sub(r"</?entml:[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"</?entml:\w*$", "", text, flags=re.IGNORECASE)
        text = text.rstrip()
    return text


def find_complete_entml_invoke_open(buffer: str) -> int:
    """返回首个含 name 且已闭合 ``>`` 的 ``<entml:invoke`` 起始下标；否则 -1。"""
    if not buffer:
        return -1
    search_from = 0
    prefix_len = len(_INVOKE_PREFIX)
    while True:
        pos = buffer.find(_INVOKE_PREFIX, search_from)
        if pos < 0:
            return -1
        close = buffer.find(">", pos + prefix_len)
        if close < 0:
            return -1
        attrs = buffer[pos + prefix_len : close]
        name = extract_attr_value(attrs, "name")
        if name and normalize_entml_name(name):
            return pos
        search_from = close + 1


def find_ambiguous_entml_tool_prefix(buffer: str) -> int:
    """thinking 块内出现工具相关 entml 前缀时，最早的下标（含未收齐的开标签）。"""
    if not buffer:
        return -1
    earliest = -1
    for prefix in _AMBIGUOUS_ENTML_PREFIXES:
        pos = buffer.find(prefix)
        if pos >= 0 and (earliest < 0 or pos < earliest):
            earliest = pos
    return earliest


def _find_plain_thinking_open(text: str, start: int = 0) -> int:
    """返回 plain ``<thinking>`` 开标签起始下标（``<entml:thinking>`` 内不含此子串）。"""
    return text.find(_PLAIN_THINKING_OPEN_PREFIX, start)


def _find_earliest_thinking_open(
    text: str,
    start: int = 0,
    *,
    thinking_enabled: bool = True,
) -> Tuple[int, bool]:
    """返回 ``(开标签下标, 是否 plain)``；无则 ``(-1, False)``。"""
    entml_at = text.find(_THINKING_OPEN_PREFIX, start)
    if not thinking_enabled:
        if entml_at < 0:
            return -1, False
        return entml_at, False
    plain_at = _find_plain_thinking_open(text, start)
    if entml_at < 0 and plain_at < 0:
        return -1, False
    if entml_at < 0:
        return plain_at, True
    if plain_at < 0:
        return entml_at, False
    if plain_at < entml_at:
        return plain_at, True
    return entml_at, False


def _find_thinking_close(
    text: str,
    body_start: int,
    *,
    opened_plain: bool,
    thinking_enabled: bool = True,
) -> Tuple[int, int]:
    """返回 ``(闭标签下标, 闭标签长度)``；未找到则 ``(-1, 0)``。"""
    if not thinking_enabled:
        close_at = text.find(_THINKING_CLOSE, body_start)
        if close_at >= 0:
            return close_at, len(_THINKING_CLOSE)
        return -1, 0

    if opened_plain:
        entml_close = text.find(_THINKING_CLOSE, body_start)
        fault_close = text.find(_FAULT_THINKING_CLOSE, body_start)
        candidates: List[Tuple[int, int]] = []
        if entml_close >= 0:
            candidates.append((entml_close, len(_THINKING_CLOSE)))
        if fault_close >= 0:
            candidates.append((fault_close, len(_FAULT_THINKING_CLOSE)))
        if not candidates:
            return -1, 0
        close_at, close_len = min(candidates, key=lambda item: item[0])
        return close_at, close_len

    entml_close = text.find(_THINKING_CLOSE, body_start)
    fault_close = text.find(_FAULT_THINKING_CLOSE, body_start)
    if entml_close >= 0 and (fault_close < 0 or entml_close <= fault_close):
        return entml_close, len(_THINKING_CLOSE)
    if fault_close < 0:
        return -1, 0

    after_fault = fault_close + len(_FAULT_THINKING_CLOSE)
    invoke_rel = find_complete_entml_invoke_open(text[after_fault:])
    entml_after = text.find(_THINKING_CLOSE, after_fault)
    if invoke_rel >= 0:
        invoke_abs = after_fault + invoke_rel
        if entml_after < 0 or invoke_abs < entml_after:
            return fault_close, len(_FAULT_THINKING_CLOSE)
    if entml_after >= 0:
        return entml_after, len(_THINKING_CLOSE)
    return -1, 0


def _hold_thinking_open_prefixes(
    buffer: str,
    *,
    thinking_enabled: bool = True,
) -> Tuple[str, str]:
    """hold ``<entml:thinking`` 或 plain ``<thinking`` 的真前缀。"""
    safe, hold = _hold_prefix(buffer, _THINKING_OPEN_PREFIX)
    if hold:
        return safe, hold
    if thinking_enabled:
        return _hold_prefix(safe, _PLAIN_THINKING_OPEN_PREFIX)
    return safe, ""


def _hold_ambiguous_tool_markup(buffer: str) -> Tuple[str, str]:
    """thinking 块内：hold 可能长成真实工具调用的 markup（非 prose ``<entml:invoke>`` 提及）。"""
    if not buffer:
        return "", ""
    hold_from: Optional[int] = None
    invoke_pos = buffer.find(_INVOKE_PREFIX)
    if invoke_pos >= 0 and entml_invoke_open_may_be_streaming(buffer, invoke_pos):
        if hold_from is None or invoke_pos < hold_from:
            hold_from = invoke_pos
    for prefix in _AMBIGUOUS_ENTML_PREFIXES:
        if prefix == _INVOKE_PREFIX:
            continue
        pos = buffer.find(prefix)
        if pos >= 0 and (hold_from is None or pos < hold_from):
            hold_from = pos
    if hold_from is not None:
        return buffer[:hold_from], buffer[hold_from:]
    lt = buffer.rfind("<")
    if lt < 0:
        return buffer, ""
    tail = buffer[lt:]
    for prefix in _AMBIGUOUS_ENTML_PREFIXES:
        if prefix.startswith(tail) and tail != prefix:
            return buffer[:lt], tail
    return buffer, ""


def has_unclosed_entml_thinking(
    text: str,
    *,
    thinking_enabled: bool = True,
) -> bool:
    """buffer 中是否存在尚未闭合的 thinking 块（含开标签未收齐）。"""
    if not text:
        return False
    i = 0
    while i < len(text):
        open_at, opened_plain = _find_earliest_thinking_open(
            text, i, thinking_enabled=thinking_enabled
        )
        if open_at < 0:
            break
        gt = text.find(">", open_at)
        if gt < 0:
            return True
        body_start = gt + 1
        close_at, close_len = _find_thinking_close(
            text,
            body_start,
            opened_plain=opened_plain,
            thinking_enabled=thinking_enabled,
        )
        if close_at < 0:
            return True
        i = close_at + close_len
    max_keep = len(_THINKING_OPEN_PREFIX) - 1
    if thinking_enabled:
        max_keep = max(max_keep, len(_PLAIN_THINKING_OPEN_PREFIX) - 1)
    check_len = min(len(text), max_keep)
    for length in range(check_len, 0, -1):
        suffix = text[-length:]
        if (
            _THINKING_OPEN_PREFIX.startswith(suffix)
            and suffix != _THINKING_OPEN_PREFIX
        ):
            if any(other.startswith(suffix) for other in _AMBIGUOUS_ENTML_PREFIXES):
                continue
            return True
        if thinking_enabled and (
            _PLAIN_THINKING_OPEN_PREFIX.startswith(suffix)
            and suffix != _PLAIN_THINKING_OPEN_PREFIX
        ):
            return True
    return False


def invoke_index_inside_unclosed_thinking(
    text: str,
    invoke_at: int,
    *,
    thinking_enabled: bool = True,
) -> bool:
    """``invoke_at`` 是否落在尚未闭合的 thinking 块内。"""
    if invoke_at < 0:
        return False
    think_open, opened_plain = _find_earliest_thinking_open(
        text, thinking_enabled=thinking_enabled
    )
    if think_open < 0 or invoke_at <= think_open:
        return False
    gt = text.find(">", think_open)
    if gt < 0:
        return True
    body_start = gt + 1
    close_at, close_len = _find_thinking_close(
        text,
        body_start,
        opened_plain=opened_plain,
        thinking_enabled=thinking_enabled,
    )
    if close_at < 0:
        return True
    return invoke_at < close_at + close_len


def split_entml_thinking(
    text: str,
    *,
    thinking_enabled: bool = True,
    preserve_visible_whitespace: bool = False,
) -> Tuple[str, str]:
    """从文本中剥离 thinking 块，返回 (正文, 思考链拼接)。"""
    if not text:
        return "", ""

    parts: List[str] = []
    clean_parts: List[str] = []
    i = 0
    while i < len(text):
        open_at, opened_plain = _find_earliest_thinking_open(
            text, i, thinking_enabled=thinking_enabled
        )
        if open_at < 0:
            clean_parts.append(text[i:])
            break

        clean_parts.append(text[i:open_at])
        gt = text.find(">", open_at)
        if gt < 0:
            clean_parts.append(text[open_at:])
            break

        body_start = gt + 1
        close_at, close_len = _find_thinking_close(
            text,
            body_start,
            opened_plain=opened_plain,
            thinking_enabled=thinking_enabled,
        )
        if close_at < 0:
            clean_parts.append(text[open_at:])
            break

        parts.append(text[body_start:close_at])
        i = close_at + close_len

    clean = "".join(clean_parts)
    thinking = "\n".join(part.strip() for part in parts if part.strip())
    if preserve_visible_whitespace:
        visible = strip_orphan_thinking_close_prefix(clean)
    else:
        visible = strip_orphan_thinking_close_prefix(clean.strip())
    return visible, thinking


def strip_orphan_thinking_close_prefix(text: str) -> str:
    """去掉可见正文开头的 orphan ``</entml:thinking>``（流式分片边界）。"""
    if not text:
        return text
    return re.sub(
        r"^\s*</entml:thinking>\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def _hold_prefix(buffer: str, tag: str) -> Tuple[str, str]:
    """若 buffer 尾部是 tag 的真前缀则 hold，否则全部可安全输出。"""
    if not buffer:
        return "", ""
    max_keep = len(tag) - 1
    check_len = min(len(buffer), max_keep)
    for length in range(check_len, 0, -1):
        suffix = buffer[-length:]
        if tag.startswith(suffix) and suffix != tag:
            return buffer[:-length], suffix
    return buffer, ""


class EntmlThinkingStreamFilter:
    """流式拆分 entml:thinking 与可见正文。

    块内正文在收到时即增量输出 thinking，无需等闭合标签。
    """

    def __init__(self, *, thinking_enabled: bool = True) -> None:
        self._thinking_enabled = thinking_enabled
        self._pending = ""
        self._in_block = False
        self._opened_plain = False
        # 当前 thinking 块是否已输出过任何内容（用于首片去前导空白）
        self._thinking_started = False
        # 见到 ``</thinking>`` 后暂存，仅当后续出现 invoke 才视为闭合；否则当纯文本
        self._fault_watch = False
        self._fault_buffer = ""

    def clear_invoke_handoff_state(self) -> None:
        """invoke 已交给正文/工具解析后，结束 thinking / fault 观察状态。"""
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._fault_buffer = ""
        self._thinking_started = False

    def in_open_thinking(self) -> bool:
        """思考块已开始且尚未闭合（含开/闭标签分片 hold）。"""
        if self._in_block or self._fault_watch:
            return True
        open_at, _ = _find_earliest_thinking_open(
            self._pending, thinking_enabled=self._thinking_enabled
        )
        if open_at >= 0:
            gt = self._pending.find(">", open_at)
            if gt < 0:
                return True
        _, hold = _hold_thinking_open_prefixes(
            self._pending, thinking_enabled=self._thinking_enabled
        )
        if hold:
            return True
        return False

    def _try_resolve_fault_watch_on_invoke(self) -> bool:
        """``</thinking>`` 之后若出现完整 invoke 开标签，则在该处结束 thinking。"""
        if not self._fault_watch or not self._fault_buffer:
            return False
        invoke_at = find_complete_entml_invoke_open(self._fault_buffer)
        if invoke_at < len(_FAULT_THINKING_CLOSE):
            return False
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = self._fault_buffer[len(_FAULT_THINKING_CLOSE) :]
        self._fault_buffer = ""
        return True

    def _try_resolve_fault_watch_on_entml_close(self, out: List[Tuple[str, str]]) -> bool:
        """未见 invoke 时出现 ``</entml:thinking>`` → ``</thinking>`` 仅为思考内纯文本。"""
        if not self._fault_watch:
            return False
        close_at = self._fault_buffer.find(_THINKING_CLOSE)
        if close_at < 0:
            return False
        emitted = self._emit_thinking_piece(self._fault_buffer[:close_at])
        if emitted:
            out.append(("thinking", emitted))
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._thinking_started = False
        self._pending = self._fault_buffer[close_at + len(_THINKING_CLOSE) :]
        self._fault_buffer = ""
        return True

    def _feed_fault_watch(self, out: List[Tuple[str, str]]) -> bool:
        """处理 ``</thinking>`` 容错观察期；返回 True 表示可继续主循环。"""
        if self._try_resolve_fault_watch_on_invoke():
            return True
        if self._try_resolve_fault_watch_on_entml_close(out):
            return True
        return False

    def _feed_in_block(self, out: List[Tuple[str, str]]) -> bool:
        """处理块内 pending；返回 False 表示应退出 feed 主循环。"""
        close_at = self._pending.find(_THINKING_CLOSE)
        if close_at >= 0:
            piece = self._pending[:close_at]
            if piece:
                emitted = self._emit_thinking_piece(piece)
                if emitted:
                    out.append(("thinking", emitted))
            self._in_block = False
            self._opened_plain = False
            self._fault_watch = False
            self._fault_buffer = ""
            self._thinking_started = False
            self._pending = self._pending[close_at + len(_THINKING_CLOSE) :]
            return True

        fault_at = self._pending.find(_FAULT_THINKING_CLOSE)
        if fault_at >= 0 and self._thinking_enabled:
            before = self._pending[:fault_at]
            if self._opened_plain:
                emitted = self._emit_thinking_piece(before)
                if emitted:
                    out.append(("thinking", emitted))
                self._in_block = False
                self._opened_plain = False
                self._fault_watch = False
                self._fault_buffer = ""
                self._thinking_started = False
                self._pending = self._pending[fault_at + len(_FAULT_THINKING_CLOSE) :]
                return True
            emitted = self._emit_thinking_piece(before)
            if emitted:
                out.append(("thinking", emitted))
            self._fault_watch = True
            self._fault_buffer = self._pending[fault_at:]
            self._pending = ""
            return False

        safe, tool_hold = _hold_ambiguous_tool_markup(self._pending)
        if tool_hold:
            if safe:
                emitted = self._emit_thinking_piece(safe)
                if emitted:
                    out.append(("thinking", emitted))
            self._pending = tool_hold
            return False

        safe, hold = _hold_prefix(self._pending, _THINKING_CLOSE)
        if not hold and self._thinking_enabled:
            safe, hold = _hold_prefix(safe, _FAULT_THINKING_CLOSE)
        if safe:
            emitted = self._emit_thinking_piece(safe)
            if emitted:
                out.append(("thinking", emitted))
        self._pending = hold
        return False

    def _feed_before_block(self, out: List[Tuple[str, str]]) -> bool:
        """开标签之前或尚未进入块；返回 False 表示应退出 feed 主循环。"""
        open_at, opened_plain = _find_earliest_thinking_open(
            self._pending, thinking_enabled=self._thinking_enabled
        )
        if open_at < 0:
            safe, self._pending = _hold_thinking_open_prefixes(
                self._pending, thinking_enabled=self._thinking_enabled
            )
            if safe:
                out.append(("content", safe))
            return False

        if open_at > 0:
            out.append(("content", self._pending[:open_at]))
            self._pending = self._pending[open_at:]

        gt = self._pending.find(">")
        if gt < 0:
            return False

        self._in_block = True
        self._opened_plain = opened_plain
        self._thinking_started = False
        self._pending = self._pending[gt + 1 :]
        return True

    def feed(self, chunk: str) -> List[Tuple[str, str]]:
        """返回 [(kind, text), ...]，kind 为 content 或 thinking。"""
        if not chunk:
            return []

        self._pending += chunk
        out: List[Tuple[str, str]] = []

        while self._pending:
            if self._fault_watch:
                self._fault_buffer += self._pending
                self._pending = ""
                if self._feed_fault_watch(out):
                    continue
                break
            if self._in_block:
                if not self._feed_in_block(out):
                    break
                continue
            if not self._feed_before_block(out):
                break

        return out

    def _emit_thinking_piece(self, piece: str) -> str:
        """输出 thinking 片段；首片去掉前导空白，与 batch strip 对齐。"""
        if not piece:
            return ""
        if not self._thinking_started:
            piece = piece.lstrip()
            if not piece:
                return ""
            self._thinking_started = True
        return piece

    def finalize(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        if self._fault_watch:
            if self._try_resolve_fault_watch_on_invoke():
                pass
            elif self._try_resolve_fault_watch_on_entml_close(out):
                pass
            else:
                emitted = self._emit_thinking_piece(self._fault_buffer)
                if emitted:
                    out.append(("thinking", emitted))
                self._fault_buffer = ""
                self._fault_watch = False
                self._in_block = False
                self._opened_plain = False
                self._thinking_started = False
        if self._in_block:
            emitted = self._emit_thinking_piece(self._pending)
            if emitted:
                out.append(("thinking", emitted))
            self._pending = ""
            self._in_block = False
            self._opened_plain = False
            self._thinking_started = False
        if self._pending:
            content, thinking = split_entml_thinking(
                self._pending, thinking_enabled=self._thinking_enabled
            )
            if thinking:
                out.append(("thinking", thinking))
            if content:
                out.append(("content", content))
            elif self._pending and not thinking:
                out.append(("content", self._pending))
        self._pending = ""
        self._in_block = False
        self._opened_plain = False
        self._fault_watch = False
        self._fault_buffer = ""
        self._thinking_started = False
        return out
