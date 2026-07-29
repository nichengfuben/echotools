from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_may_be_streaming,
    find_actionable_entml_invoke_open,
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


def find_complete_entml_invoke_open(
    buffer: str,
    *,
    known_names: Optional[set[str]] = None,
) -> int:
    """返回首个可解析 ``<entml:invoke`` 起始下标；否则 ``-1``。"""
    return find_actionable_entml_invoke_open(buffer, known_names=known_names)



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



def tool_markup_follows_entml_thinking_close(text: str) -> bool:
    """thinking 闭标签之后（允许中间有简短可见正文）是否出现真实工具 markup。"""
    if not text:
        return False
    if re.match(
        r"^\s*(?:<tool\s*>|<entml:invoke\b)",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(
        re.search(r"<tool\s*>|<entml:invoke\b", text, re.IGNORECASE),
    )


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
        after_entml = text[entml_after + len(_THINKING_CLOSE) :]
        if tool_markup_follows_entml_thinking_close(after_entml):
            return fault_close, len(_FAULT_THINKING_CLOSE)
        return entml_after, len(_THINKING_CLOSE)
    if tool_markup_follows_entml_thinking_close(text[after_fault:]):
        return fault_close, len(_FAULT_THINKING_CLOSE)
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


def _hold_ambiguous_tool_markup(
    buffer: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """thinking 块内：hold 可能长成真实工具调用的 markup（非 prose ``<entml:invoke>`` 提及）。"""
    if not buffer:
        return "", ""
    hold_from: Optional[int] = None
    invoke_pos = buffer.find(_INVOKE_PREFIX)
    if invoke_pos >= 0 and entml_invoke_open_may_be_streaming(
        buffer, invoke_pos, known_names=known_names
    ):
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
    return invoke_index_inside_any_thinking_block(
        text, invoke_at, thinking_enabled=thinking_enabled, unclosed_only=True,
    )


def invoke_index_inside_any_thinking_block(
    text: str,
    invoke_at: int,
    *,
    thinking_enabled: bool = True,
    unclosed_only: bool = False,
) -> bool:
    """``invoke_at`` 是否落在 thinking 块内（``unclosed_only`` 时仅检查未闭合块）。"""
    if invoke_at < 0:
        return False
    i = 0
    while i < len(text):
        open_at, opened_plain = _find_earliest_thinking_open(
            text, i, thinking_enabled=thinking_enabled,
        )
        if open_at < 0:
            break
        gt = text.find(">", open_at)
        if gt < 0:
            return invoke_at > open_at
        body_start = gt + 1
        close_at, close_len = _find_thinking_close(
            text,
            body_start,
            opened_plain=opened_plain,
            thinking_enabled=thinking_enabled,
        )
        if close_at < 0:
            if open_at < invoke_at:
                return True
            break
        block_end = close_at + close_len
        if open_at < invoke_at < block_end:
            return True
        if unclosed_only:
            return False
        i = block_end
    return False

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

