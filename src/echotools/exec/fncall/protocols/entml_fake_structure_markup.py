"""剥离模型误生成的 entml 顶层结构标签与 Tool Result ID 注释。"""

from __future__ import annotations

import re
from typing import Tuple

from echotools.exec.fncall.protocols.entml_tool_result_comment import (
    leading_partial_tool_result_id_comment_len,
    strip_complete_tool_result_id_comments,
    trailing_partial_tool_result_id_comment_len,
)

# 开/闭标签在 ``>`` 闭合即剥离；``funtions_results`` 拼写与 prompt 注入一致。
_FAKE_ENTML_OPEN_TAG_RES = (
    ("result", re.compile(r"<entml:result\b[^>]*>", re.IGNORECASE)),
    (
        "funtions_results",
        re.compile(r"<entml:funtions_results\b[^>]*>", re.IGNORECASE),
    ),
    (
        "conversation_history",
        re.compile(r"<entml:conversation_history\b[^>]*>", re.IGNORECASE),
    ),
)
_FAKE_ENTML_CLOSE_TAG_RES = (
    ("result", re.compile(r"</entml:result\s*>", re.IGNORECASE)),
    (
        "funtions_results",
        re.compile(r"</entml:funtions_results\s*>", re.IGNORECASE),
    ),
    (
        "conversation_history",
        re.compile(r"</entml:conversation_history\s*>", re.IGNORECASE),
    ),
)
_ENTML_RESULT_BLOCK_RE = re.compile(
    r"<entml:result\b[^>]*>[\s\S]*?</entml:result\s*>",
    re.IGNORECASE,
)

_FAKE_ENTML_TAG_PREFIXES: Tuple[str, ...] = (
    "<entml:result",
    "</entml:result",
    "<entml:funtions_results",
    "</entml:funtions_results",
    "<entml:conversation_history",
    "</entml:conversation_history",
)


def _strip_complete_fake_entml_tags(text: str) -> Tuple[str, bool]:
    found = False
    for _, pattern in _FAKE_ENTML_OPEN_TAG_RES + _FAKE_ENTML_CLOSE_TAG_RES:
        text, n = pattern.subn("", text)
        if n:
            found = True
    return text, found


def _strip_fake_entml_result_blocks(text: str) -> Tuple[str, bool]:
    text, n = _ENTML_RESULT_BLOCK_RE.subn("", text)
    return text, n > 0


def _could_be_fake_entml_tag_prefix(fragment: str) -> bool:
    frag = fragment.lower()
    if not frag.startswith("<"):
        return False
    if ">" in frag:
        return False
    for prefix in _FAKE_ENTML_TAG_PREFIXES:
        pl = prefix.lower()
        if pl.startswith(frag) or frag.startswith(pl):
            return True
    return False


def trailing_partial_fake_entml_structure_len(text: str) -> int:
    """尾部未收齐至 ``>`` 的伪 entml 结构标签应 hold 的字节数。"""
    hold = trailing_partial_tool_result_id_comment_len(text)
    if hold:
        return hold
    lt = text.rfind("<")
    if lt < 0:
        return 0
    suffix = text[lt:]
    if ">" in suffix:
        return 0
    if _could_be_fake_entml_tag_prefix(suffix):
        return len(suffix)
    return 0


def leading_partial_fake_entml_structure_len(text: str) -> int:
    """开头未收齐至 ``>`` 的伪 entml 结构标签应 hold 的字节数。"""
    hold = leading_partial_tool_result_id_comment_len(text)
    if hold:
        return hold
    stripped = text.lstrip()
    if not stripped.startswith("<"):
        return 0
    if ">" in stripped:
        return 0
    if _could_be_fake_entml_tag_prefix(stripped):
        return len(text)
    return 0


def _truncate_unclosed_fake_result_tail(text: str) -> Tuple[str, bool]:
    """流式：从 ``<entml:result`` 起至 ``</entml:result>`` 收齐前均不可见。"""
    found = False
    search_from = 0
    while True:
        open_m = re.search(r"<entml:result\b", text[search_from:], re.IGNORECASE)
        if not open_m:
            break
        abs_start = search_from + open_m.start()
        gt = text.find(">", abs_start)
        if gt < 0:
            text = text[:abs_start]
            found = True
            break
        abs_end = gt + 1
        tail = text[abs_end:]
        close_m = re.search(r"</entml:result\s*>", tail, re.IGNORECASE)
        if close_m:
            search_from = abs_end + close_m.end()
            continue
        text = text[:abs_start]
        found = True
        break
    return text, found


def strip_fake_entml_structure_markup(content: str) -> Tuple[str, bool]:
    """batch：剥离完整伪 entml 结构标签、result 块与 Tool Result ID 注释。"""
    if not content:
        return content, False
    found = False
    text = strip_complete_tool_result_id_comments(content)
    if text != content:
        found = True
    text, hit = _strip_fake_entml_result_blocks(text)
    found = found or hit
    text, hit = _truncate_unclosed_fake_result_tail(text)
    found = found or hit
    text, hit = _strip_complete_fake_entml_tags(text)
    found = found or hit
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, found


def strip_fake_entml_structure_markup_for_display(content: str) -> Tuple[str, bool]:
    """流式 ``partial_text``：hold 未收齐标签 + 截断未闭合 result + 剥离完整片段。"""
    if not content:
        return content, False
    found = False
    tail_hold = trailing_partial_fake_entml_structure_len(content)
    text = content[:-tail_hold] if tail_hold else content
    if tail_hold:
        found = True
    text, hit = _truncate_unclosed_fake_result_tail(text)
    found = found or hit
    text, hit = strip_fake_entml_structure_markup(text)
    found = found or hit
    tail_hold2 = trailing_partial_fake_entml_structure_len(text)
    if tail_hold2:
        text = text[:-tail_hold2]
        found = True
    return text, found
