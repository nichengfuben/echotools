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


def _orphan_close_re(tag: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|\n)([\s\S]*?)\n\s*</{tag}\s*>\s*(?:\n|$)",
        re.IGNORECASE,
    )


def _orphan_open_re(tag: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|\n)\s*<{tag}\s*>\s*\n[\s\S]*$",
        re.IGNORECASE,
    )


def _split_entml_invoke_protected(segment: str) -> List[Tuple[str, bool]]:
    """按 ``<entml:invoke>`` 切分；invoke 块（含未闭合尾部）不参与伪 history 剥离。"""
    if not segment:
        return []
    parts: List[Tuple[str, bool]] = []
    i = 0
    while i < len(segment):
        open_m = _ENTML_INVOKE_OPEN_RE.search(segment, i)
        if not open_m:
            parts.append((segment[i:], False))
            break
        if open_m.start() > i:
            parts.append((segment[i : open_m.start()], False))
        block_m = _ENTML_INVOKE_BLOCK_RE.match(segment, open_m.start())
        if block_m:
            parts.append((block_m.group(0), True))
            i = block_m.end()
        else:
            parts.append((segment[open_m.start() :], True))
            break
    return parts


def _open_before_entml_re(tag: str) -> re.Pattern[str]:
    """``<tool>\\n…`` 未闭合但在 ``<entml:invoke`` 前 — 整段剥离。"""
    return re.compile(
        rf"<{tag}\s*>\s*\n[\s\S]*?(?=<entml:invoke\b)",
        re.IGNORECASE,
    )


def _orphan_open_to_eof_re(tag: str) -> re.Pattern[str]:
    """未闭合伪块直到段末（下一段为 ``<entml:invoke>`` 时）。"""
    return re.compile(
        rf"<{tag}\s*>\s*\n[\s\S]*$",
        re.IGNORECASE,
    )


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
        for pair_re in (_paired_block_re(tag), _paired_block_anywhere_re(tag)):
            while True:
                new_text, n = pair_re.subn("", text, count=1)
                if n == 0:
                    break
                found = True
                text = new_text
        before_entml = _open_before_entml_re(tag)
        while True:
            new_text, n = before_entml.subn("", text, count=1)
            if n == 0:
                break
            found = True
            text = new_text
        if followed_by_invoke:
            to_eof = _orphan_open_to_eof_re(tag)
            while True:
                new_text, n = to_eof.subn("", text, count=1)
                if n == 0:
                    break
                found = True
                text = new_text
        close_re = _orphan_close_re(tag)
        while True:
            new_text, n = close_re.subn("\n", text, count=1)
            if n == 0:
                break
            found = True
            text = new_text
        open_re = _orphan_open_re(tag)
        while True:
            new_text, n = open_re.subn("", text, count=1)
            if n == 0:
                break
            found = True
            text = new_text
    if not _PLAIN_THINKING_OPEN_LINE_RE.search(text):
        while True:
            new_text, n = _ORPHAN_FAULT_THINKING_CLOSE_LINE_RE.subn("\n", text, count=1)
            if n == 0:
                break
            found = True
            text = new_text
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


def strip_fake_history_markup_for_display(content: str) -> Tuple[str, bool]:
    """流式 ``partial_text`` 用：完整块剥离 + 截断行尾未收齐的伪标签。"""
    cleaned, found = strip_fake_history_markup(content)
    invoke_m = _ENTML_INVOKE_OPEN_RE.search(cleaned)
    if invoke_m and "</entml:invoke>" not in cleaned[invoke_m.start() :]:
        return cleaned, found
    tail = re.search(
        r"(?:^|\n)\s*(?:</?(?:assistant|tool)\b[^\n]*|</thinking>\s*(?:<(?:assistant|tool)\b[^\n]*)?)$",
        cleaned,
        re.IGNORECASE | re.MULTILINE,
    )
    if tail:
        cleaned = cleaned[: tail.start()]
        found = True
    else:
        glued = re.search(
            r"</thinking>\s*<(?:assistant|tool)\b[^\n]*$",
            cleaned,
            re.IGNORECASE,
        )
        if glued:
            cleaned = cleaned[: glued.start()]
            found = True
    return cleaned, found
