"""检测并剥离模型误输出的 conversation history 伪标签（``<assistant>`` / ``<tool>``）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from echotools.exec.fncall.shared.normalization import normalize_content

_FAKE_HISTORY_TAGS = ("assistant", "tool")
_FAKE_MARKUP_BLOCK_DETECT_RE = re.compile(
    r"(?:^|\n)\s*</?(?:assistant|tool)\s*>\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_ENTML_THINKING_OPEN_RE = re.compile(
    r"<entml:thinking\b[^>]*>",
    re.IGNORECASE,
)
_ENTML_THINKING_CLOSE = "</entml:thinking>"
_ORPHAN_FAULT_THINKING_CLOSE_LINE_RE = re.compile(
    r"(?:^|\n)\s*</thinking>\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_PLAIN_THINKING_OPEN_LINE_RE = re.compile(
    r"(?:^|\n)\s*<thinking\s*>\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_ENTML_INVOKE_OPEN_RE = re.compile(
    r"<entml:invoke\b",
    re.IGNORECASE,
)
_ENTML_INVOKE_BLOCK_RE = re.compile(
    r"<entml:invoke\b[^>]*>[\s\S]*?</entml:invoke>",
    re.IGNORECASE,
)
_ENTML_FUNCTION_CALLS_OPEN_RE = re.compile(
    r"<entml:function_calls\b",
    re.IGNORECASE,
)
_ENTML_FUNCTION_CALLS_BLOCK_RE = re.compile(
    r"<entml:function_calls\b[^>]*>[\s\S]*?</entml:function_calls>",
    re.IGNORECASE,
)
_ENTML_FUNCTION_CALLS_CLOSE = "</entml:function_calls>"


class HistoryMarkupDetectionResult:
    """伪 history 标签检测结果。"""

    __slots__ = ("detected", "suggestion")

    def __init__(self, detected: bool, suggestion: str = "") -> None:
        self.detected = detected
        self.suggestion = suggestion


_HISTORY_MARKUP_SUGGESTION = (
    "Do NOT output <assistant> or <tool> blocks in your reply. "
    "Those tags are reserved for injected conversation history only. "
    "Use <entml:thinking> for private reasoning and <entml:invoke> for tool calls. "
    "Write visible replies as plain text without history markup."
)


def detect_fake_history_markup(
    messages: List[Dict[str, Any]],
) -> HistoryMarkupDetectionResult:
    """扫描 assistant 正文是否误含块级 ``<assistant>`` / ``<tool>`` 伪标签。"""
    for msg in messages:
        if (msg.get("role") or "") != "assistant":
            continue
        content = normalize_content(msg.get("content", ""))
        if content and _FAKE_MARKUP_BLOCK_DETECT_RE.search(content):
            return HistoryMarkupDetectionResult(True, _HISTORY_MARKUP_SUGGESTION)
    return HistoryMarkupDetectionResult(False, "")


def _paired_block_re(tag: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|\n)\s*<{tag}\s*>\s*\n[\s\S]*?\n\s*</{tag}\s*>",
        re.IGNORECASE,
    )


def _paired_block_anywhere_re(tag: str) -> re.Pattern[str]:
    """``<tool>\\n…\\n</tool>`` 即使前缀无换行（流式分片边界）也剥离。"""
    return re.compile(
        rf"<{tag}\s*>\s*\n[\s\S]*?\n\s*</{tag}\s*>",
        re.IGNORECASE,
    )


def _paired_block_glued_brace_re(tag: str) -> re.Pattern[str]:
    """``<tool>{Tool: ...}</tool>`` 无内嵌换行伪块（流式分片常压成单行）。"""
    return re.compile(
        rf"<{tag}\s*>\s*\{{[\s\S]*?\}}\s*</{tag}\s*>",
        re.IGNORECASE,
    )


def _orphan_close_line_re(tag: str) -> re.Pattern[str]:
    """无配对开标签的 ``</tag>`` 行：仅删该行，不删其前的合法可见正文。"""
    return re.compile(
        rf"^\s*</{tag}\s*>\s*$",
        re.IGNORECASE | re.MULTILINE,
    )


def _orphan_open_re(tag: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|\n)\s*<{tag}\s*>\s*\n[\s\S]*$",
        re.IGNORECASE,
    )


def _split_entml_invoke_protected(segment: str) -> List[Tuple[str, bool]]:
    """按 ``<entml:function_calls>`` / ``<entml:invoke>`` 切分；保护区不参与伪 history 剥离。"""
    if not segment:
        return []
    parts: List[Tuple[str, bool]] = []
    i = 0
    while i < len(segment):
        fc_m = _ENTML_FUNCTION_CALLS_OPEN_RE.search(segment, i)
        inv_m = _ENTML_INVOKE_OPEN_RE.search(segment, i)
        candidates = [m for m in (fc_m, inv_m) if m]
        if not candidates:
            parts.append((segment[i:], False))
            break
        open_m = min(candidates, key=lambda m: m.start())
        if open_m.start() > i:
            parts.append((segment[i : open_m.start()], False))
        if open_m is fc_m:
            block_m = _ENTML_FUNCTION_CALLS_BLOCK_RE.match(segment, open_m.start())
        else:
            block_m = _ENTML_INVOKE_BLOCK_RE.match(segment, open_m.start())
        if block_m:
            parts.append((block_m.group(0), True))
            i = block_m.end()
        else:
            parts.append((segment[open_m.start() :], True))
            break
    return parts


def _open_before_entml_re(tag: str) -> re.Pattern[str]:
    """``<tool>\\n…`` 未闭合但在 ``<entml:(function_calls|invoke)`` 前 — 整段剥离。"""
    return re.compile(
        rf"<{tag}\s*>\s*\n[\s\S]*?(?=<entml:(?:function_calls|invoke)\b)",
        re.IGNORECASE,
    )


def _orphan_open_to_eof_re(tag: str) -> re.Pattern[str]:
    """未闭合伪块直到段末（下一段为 ``<entml:invoke>`` 时）。"""
    return re.compile(
        rf"<{tag}\s*>\s*\n[\s\S]*$",
        re.IGNORECASE,
    )


def _subn_all(pattern, text: str, repl: str = "") -> Tuple[str, bool]:
    found = False
    while True:
        new_text, n = pattern.subn(repl, text, count=1)
        if n == 0:
            return text, found
        found = True
        text = new_text


def _strip_one_fake_tag(
    text: str,
    tag: str,
    *,
    followed_by_invoke: bool,
) -> Tuple[str, bool]:
    found = False
    for pair_re in (
        _paired_block_re(tag),
        _paired_block_anywhere_re(tag),
        _paired_block_glued_brace_re(tag),
    ):
        text, hit = _subn_all(pair_re, text)
        found = found or hit
    text, hit = _subn_all(_open_before_entml_re(tag), text)
    found = found or hit
    if followed_by_invoke:
        text, hit = _subn_all(_orphan_open_to_eof_re(tag), text)
        found = found or hit
    text, hit = _subn_all(_orphan_close_line_re(tag), text)
    found = found or hit
    text, hit = _subn_all(_orphan_open_re(tag), text)
    return text, found or hit


def _strip_fake_blocks_in_unprotected(
    segment: str,
    *,
    followed_by_invoke: bool = False,
) -> Tuple[str, bool]:
    if not segment:
        return segment, False
    found = False
    text = segment
    for tag in _FAKE_HISTORY_TAGS:
        text, hit = _strip_one_fake_tag(
            text, tag, followed_by_invoke=followed_by_invoke
        )
        found = found or hit
    if not _PLAIN_THINKING_OPEN_LINE_RE.search(text):
        text, hit = _subn_all(_ORPHAN_FAULT_THINKING_CLOSE_LINE_RE, text, "\n")
        found = found or hit
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, found


def _strip_fake_blocks_in_segment(segment: str) -> Tuple[str, bool]:
    if not segment:
        return segment, False
    parts = _split_entml_invoke_protected(segment)
    if len(parts) == 1 and parts[0][1]:
        return segment, False
    out: List[str] = []
    found = False
    for idx, (chunk, protected) in enumerate(parts):
        if protected:
            out.append(chunk)
            continue
        next_is_invoke = idx + 1 < len(parts) and parts[idx + 1][1]
        cleaned, hit = _strip_fake_blocks_in_unprotected(
            chunk,
            followed_by_invoke=next_is_invoke,
        )
        out.append(cleaned)
        found = found or hit
    return "".join(out), found


def strip_fake_history_markup(content: str) -> Tuple[str, bool]:
    """剥离块级伪 ``<assistant>`` / ``<tool>``；``<entml:thinking>`` 区域原样保留。"""
    if not content:
        return content, False

    parts: List[str] = []
    found = False
    i = 0
    while i < len(content):
        open_m = _ENTML_THINKING_OPEN_RE.search(content, i)
        if not open_m:
            chunk, hit = _strip_fake_blocks_in_segment(content[i:])
            parts.append(chunk)
            found = found or hit
            break

        if open_m.start() > i:
            chunk, hit = _strip_fake_blocks_in_segment(content[i : open_m.start()])
            parts.append(chunk)
            found = found or hit

        body_start = open_m.end()
        close_at = content.find(_ENTML_THINKING_CLOSE, body_start)
        if close_at >= 0:
            parts.append(content[open_m.start() : close_at + len(_ENTML_THINKING_CLOSE)])
            i = close_at + len(_ENTML_THINKING_CLOSE)
        else:
            parts.append(content[open_m.start() :])
            break

    return "".join(parts), found


def _truncate_display_fake_tail(cleaned: str) -> Tuple[str, bool]:
    found = False
    tail = re.search(
        r"(?:^|\n)\s*(?:</?(?:assistant|tool)\b[^\n]*|</thinking>\s*(?:<(?:assistant|tool)\b[^\n]*)?)$",
        cleaned,
        re.IGNORECASE | re.MULTILINE,
    )
    if tail:
        return cleaned[: tail.start()], True
    glued = re.search(
        r"</thinking>\s*<(?:assistant|tool)\b[^\n]*$",
        cleaned,
        re.IGNORECASE,
    )
    if glued:
        cleaned, found = cleaned[: glued.start()], True
    glued_open = re.search(
        r"(?:^|\n)\s*<(?:assistant|tool)\b[^>]*>?\s*(?:\{[^\n<]*)?$",
        cleaned,
        re.IGNORECASE | re.MULTILINE,
    )
    if glued_open:
        cleaned, found = cleaned[: glued_open.start()], True
    partial_fake_close = re.search(
        r"(?:^|\n)\s*<(?:assistant|tool)\b[^>]*>"
        r"(?:[\s\S]*?(?:</(?:assistant|tool)\b[^>]*)?)?$",
        cleaned,
        re.IGNORECASE | re.MULTILINE,
    )
    if partial_fake_close:
        cleaned, found = cleaned[: partial_fake_close.start()], True
    return cleaned, found


def strip_fake_history_markup_for_display(content: str) -> Tuple[str, bool]:
    """流式 ``partial_text`` 用：完整块剥离 + 截断行尾未收齐的伪标签。"""
    cleaned, found = strip_fake_history_markup(content)
    invoke_m = _ENTML_INVOKE_OPEN_RE.search(cleaned)
    fc_m = _ENTML_FUNCTION_CALLS_OPEN_RE.search(cleaned)
    if invoke_m and fc_m:
        prot_m = invoke_m if invoke_m.start() <= fc_m.start() else fc_m
    else:
        prot_m = invoke_m or fc_m
    if prot_m:
        tail = cleaned[prot_m.start() :]
        invoke_open = _ENTML_INVOKE_OPEN_RE.search(tail)
        if invoke_open and "</entml:invoke>" not in tail[invoke_open.start() :]:
            return cleaned, found
        if (
            _ENTML_FUNCTION_CALLS_OPEN_RE.search(tail)
            and _ENTML_FUNCTION_CALLS_CLOSE not in tail
        ):
            return cleaned, found
    cleaned2, hit = _truncate_display_fake_tail(cleaned)
    return cleaned2, found or hit
