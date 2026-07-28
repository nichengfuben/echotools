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


def _strip_fake_blocks_in_segment(segment: str) -> Tuple[str, bool]:
    if not segment:
        return segment, False
    found = False
    text = segment
    for tag in _FAKE_HISTORY_TAGS:
        pair_re = _paired_block_re(tag)
        while True:
            new_text, n = pair_re.subn("", text, count=1)
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
    tail = re.search(
        r"(?:^|\n)\s*(?:</?(?:assistant|tool)\b[^\n]*|</thinking>\s*)$",
        cleaned,
        re.IGNORECASE | re.MULTILINE,
    )
    if tail:
        cleaned = cleaned[: tail.start()]
        found = True
    return cleaned, found
