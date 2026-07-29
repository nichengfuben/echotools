"""剥离模型误生成的 entml 顶层结构标签与 Tool Result ID 注释。"""

from __future__ import annotations

import re
from typing import Tuple

from echotools.exec.fncall.protocols.entml_tool_result_comment import (
    leading_partial_tool_result_id_comment_len,
    strip_complete_tool_result_id_comments,
    trailing_partial_tool_result_id_comment_len,
)

# Step 1：带 id 的 result 整块（含内部正文）剥离。
_ENTML_RESULT_ID_BLOCK_RE = re.compile(
    r"<entml:result\b[^>]*\bid\s*=[^>]*>[\s\S]*?</entml:result\s*>",
    re.IGNORECASE,
)
_ENTML_RESULT_ID_OPEN_INNER_RE = re.compile(
    r"<entml:result\b[^>]*\bid\s*=",
    re.IGNORECASE,
)

# Step 2：仅剥离开/闭标签（``>`` 闭合即移除，不删标签间/后正文）。
_TAG_ONLY_OPEN_RES = (
    re.compile(r"<entml:funtions_results\b[^>]*>", re.IGNORECASE),
    re.compile(r"<entml:conversation_history\b[^>]*>", re.IGNORECASE),
    re.compile(r"<entml:calls\b[^>]*>", re.IGNORECASE),
    re.compile(r"<entml:call\b[^>]*>", re.IGNORECASE),
    re.compile(r"<function_calling_behavior\b[^>]*>", re.IGNORECASE),
    re.compile(r"<thinking_behavior\b[^>]*>", re.IGNORECASE),
    re.compile(r"<entml:result\b[^>]*>", re.IGNORECASE),
)
_TAG_ONLY_CLOSE_RES = (
    re.compile(r"</entml:funtions_results\s*>", re.IGNORECASE),
    re.compile(r"</entml:conversation_history\s*>", re.IGNORECASE),
    re.compile(r"</entml:calls\s*>", re.IGNORECASE),
    re.compile(r"</entml:call\s*>", re.IGNORECASE),
    re.compile(r"</function_calling_behavior\s*>", re.IGNORECASE),
    re.compile(r"</thinking_behavior\s*>", re.IGNORECASE),
    re.compile(r"</entml:result\s*>", re.IGNORECASE),
)

_FAKE_ENTML_TAG_PREFIXES: Tuple[str, ...] = (
    "<entml:result",
    "</entml:result",
    "<entml:funtions_results",
    "</entml:funtions_results",
    "<entml:conversation_history",
    "</entml:conversation_history",
    "<entml:calls",
    "</entml:calls",
    "<entml:call",
    "</entml:call",
    "<function_calling_behavior",
    "</function_calling_behavior",
    "<thinking_behavior",
    "</thinking_behavior",
    "</entml:invoke",
    "</entml:parameter",
    "</entml:thinking",
)

# 模型误输出的残缺/单行 ``</entml:…``（无完整闭标签名或未收齐 ``>``）。
_ORPHAN_ENTML_CLOSE_LINE_RE = re.compile(
    r"(?m)^\s*(?:●\s*)?</entml:?[a-z0-9_-]*\s*$",
    re.IGNORECASE,
)
_TRAILING_INCOMPLETE_ENTML_CLOSE_RE = re.compile(
    r"</entml:?[a-z0-9_-]*\s*$",
    re.IGNORECASE,
)


def _strip_fake_entml_result_id_blocks(text: str) -> Tuple[str, bool]:
    text, n = _ENTML_RESULT_ID_BLOCK_RE.subn("", text)
    return text, n > 0


def _strip_tag_only_markup(text: str) -> Tuple[str, bool]:
    found = False
    for pattern in _TAG_ONLY_OPEN_RES + _TAG_ONLY_CLOSE_RES:
        text, n = pattern.subn("", text)
        if n:
            found = True
    return text, found


def _strip_orphan_entml_close_leaks(text: str) -> Tuple[str, bool]:
    text, n1 = _ORPHAN_ENTML_CLOSE_LINE_RE.subn("", text)
    text, n2 = _TRAILING_INCOMPLETE_ENTML_CLOSE_RE.subn("", text)
    return text, (n1 + n2) > 0


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


def _truncate_unclosed_fake_result_id_tail(text: str) -> Tuple[str, bool]:
    """流式/batch：``<entml:result id=...>`` 未闭合至 ``</entml:result>`` 前均不可见。"""
    found = False
    search_from = 0
    while True:
        open_m = _ENTML_RESULT_ID_OPEN_INNER_RE.search(text[search_from:])
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
    """batch：id result 整块 → 仅标签 → Tool Result ID 注释。"""
    if not content:
        return content, False
    found = False
    text = strip_complete_tool_result_id_comments(content)
    if text != content:
        found = True
    text, hit = _strip_fake_entml_result_id_blocks(text)
    found = found or hit
    text, hit = _truncate_unclosed_fake_result_id_tail(text)
    found = found or hit
    text, hit = _strip_tag_only_markup(text)
    found = found or hit
    text, hit = _strip_orphan_entml_close_leaks(text)
    found = found or hit
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, found


def strip_fake_entml_structure_markup_for_display(content: str) -> Tuple[str, bool]:
    """流式 ``partial_text``：hold 未收齐标签 + 截断未闭合 id result + 剥离。"""
    if not content:
        return content, False
    found = False
    tail_hold = trailing_partial_fake_entml_structure_len(content)
    text = content[:-tail_hold] if tail_hold else content
    if tail_hold:
        found = True
    text, hit = _truncate_unclosed_fake_result_id_tail(text)
    found = found or hit
    text, hit = strip_fake_entml_structure_markup(text)
    found = found or hit
    tail_hold2 = trailing_partial_fake_entml_structure_len(text)
    if tail_hold2:
        text = text[:-tail_hold2]
        found = True
    return text, found
