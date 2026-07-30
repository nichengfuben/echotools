from __future__ import annotations

import re
from typing import List, Tuple

from echotools.exec.fncall.protocols.entml_fake_structure_markup import (
    leading_partial_fake_entml_structure_len,
    strip_fake_entml_structure_markup_for_display,
    trailing_partial_fake_entml_structure_len,
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


from echotools.exec.fncall.protocols.entml_think.filter import EntmlThinkingStreamFilter
from echotools.exec.fncall.protocols.entml_think.hold import (
    _find_earliest_thinking_open,
    _find_thinking_close,
    find_complete_entml_invoke_open,
    has_unclosed_entml_thinking,
    invoke_index_inside_any_thinking_block,
    invoke_index_inside_unclosed_thinking,
    tool_markup_follows_entml_thinking_close,
)

__all__ = [
    "EntmlThinkingStreamFilter",
    "find_complete_entml_invoke_open",
    "has_unclosed_entml_thinking",
    "invoke_index_inside_any_thinking_block",
    "invoke_index_inside_unclosed_thinking",
    "split_entml_thinking",
]

def leading_entml_tag_holdback_len(
    text: str,
    *,
    thinking_enabled: bool = True,
) -> int:
    """buffer 开头是 entml/thinking/invoke 标签真前缀时，应 hold 的字节数。"""
    if not text:
        return 0
    comment_hold = leading_partial_fake_entml_structure_len(text)
    if comment_hold:
        return comment_hold
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
    if thinking_enabled:
        visible, thinking = split_entml_thinking(buf, thinking_enabled=True)
        if thinking:
            return visible
    return buf


def trailing_entml_tag_holdback_len(text: str) -> int:
    """buffer 尾部是 entml/thinking 标签真前缀时，应 hold 的字节数。"""
    if not text:
        return 0
    comment_hold = trailing_partial_fake_entml_structure_len(text)
    if comment_hold:
        return comment_hold
    invoke_idx = text.rfind("<entml:invoke")
    if invoke_idx >= 0:
        tail_from_invoke = text[invoke_idx:]
        if ">" not in tail_from_invoke:
            return len(tail_from_invoke)
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


def _strip_stream_tool_entml_tags(text: str) -> str:
    """流式可见区：仅去掉带属性的工具标签；保留 prose ``<entml:invoke>`` 提及。"""
    text = re.sub(
        r"<entml:(?:invoke|parameter|parameters|function_calls)\s[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</entml:(?:invoke|parameter|parameters|function_calls)\s*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<entml:(?:invoke|parameter|parameters|function_calls)\s[^>]*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text


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
    text = strip_fake_entml_structure_markup_for_display(text)[0]
    if has_calls:
        text = text.rstrip()
    if not text.strip():
        return ""
    if re.search(r"</?entml:", text, re.IGNORECASE):
        if thinking_enabled:
            text = _strip_stream_tool_entml_tags(text)
        else:
            text = re.sub(r"</?entml:[^>]*>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"</?entml:\w*$", "", text, flags=re.IGNORECASE)
        text = text.rstrip()
    return text


def _advance_past_fault_thinking_close(
    text: str,
    i: int,
    *,
    close_len: int,
    opened_plain: bool,
    thinking_enabled: bool,
    clean_parts: List[str],
) -> int:
    if (
        close_len != len(_FAULT_THINKING_CLOSE)
        or opened_plain
        or not thinking_enabled
    ):
        return i
    entml_after = text.find(_THINKING_CLOSE, i)
    if entml_after < 0:
        return i
    after_entml = text[entml_after + len(_THINKING_CLOSE) :]
    if tool_markup_follows_entml_thinking_close(after_entml):
        clean_parts.append(text[i:entml_after])
        return entml_after + len(_THINKING_CLOSE)
    return i


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
        i = _advance_past_fault_thinking_close(
            text,
            close_at + close_len,
            close_len=close_len,
            opened_plain=opened_plain,
            thinking_enabled=thinking_enabled,
            clean_parts=clean_parts,
        )
    clean = "".join(clean_parts)
    thinking = "\n".join(part.strip() for part in parts if part.strip())
    visible_src = clean if preserve_visible_whitespace else clean.strip()
    return strip_orphan_thinking_close_prefix(visible_src), thinking


def strip_orphan_thinking_close_prefix(text: str) -> str:
    """去掉可见正文开头/末尾的 orphan ``</entml:thinking>``（流式分片边界）。"""
    if not text:
        return text
    text = re.sub(
        r"^\s*</entml:thinking>\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"\s*</entml:thinking>\s*$",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )


