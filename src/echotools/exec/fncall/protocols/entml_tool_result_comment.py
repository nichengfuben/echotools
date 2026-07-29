"""剥离模型误生成的 ``<!-- Tool Result ID:… -->``（仅 history 注入合法）。"""

from __future__ import annotations

import re

# 与 format_tool_result_id_comment() 输出格式一致；允许空白变化。
_TOOL_RESULT_ID_COMMENT_RE = re.compile(
    r"<!--\s*Tool\s+Result\s+ID\s*:\s*.*?-->",
    re.IGNORECASE | re.DOTALL,
)

_MARKER_LOWER = "<!-- tool result id:"


def _could_be_tool_result_id_comment_open(fragment: str) -> bool:
    """``fragment`` 以 ``<!--`` 开头且可能长成 Tool Result ID 注释（未闭合）。"""
    frag = fragment.strip().lower()
    if not frag.startswith("<!--"):
        return False
    if "-->" in frag:
        return False
    return _MARKER_LOWER.startswith(frag) or frag.startswith(_MARKER_LOWER)


def strip_complete_tool_result_id_comments(text: str) -> str:
    """移除已完整闭合的 Tool Result ID HTML 注释。"""
    if not text:
        return ""
    return _TOOL_RESULT_ID_COMMENT_RE.sub("", text)


def trailing_partial_tool_result_id_comment_len(text: str) -> int:
    """尾部未闭合的 Tool Result ID 注释应 hold 的字节数（含 ``<!--`` 起）。"""
    if not text:
        return 0
    idx = text.rfind("<!--")
    if idx < 0:
        return 0
    suffix = text[idx:]
    if "-->" in suffix:
        return 0
    if _could_be_tool_result_id_comment_open(suffix):
        return len(suffix)
    return 0


def leading_partial_tool_result_id_comment_len(text: str) -> int:
    """开头未闭合的 Tool Result ID 注释应 hold 的字节数。"""
    if not text:
        return 0
    stripped = text.lstrip()
    if not stripped.startswith("<!--"):
        return 0
    if "-->" in stripped:
        return 0
    if _could_be_tool_result_id_comment_open(stripped):
        return len(text)
    return 0


def strip_tool_result_id_comments_for_display(text: str) -> str:
    """流式可见区：去掉完整注释；截断尾部未闭合的伪注释。"""
    if not text:
        return ""
    cleaned = strip_complete_tool_result_id_comments(text)
    tail_hold = trailing_partial_tool_result_id_comment_len(cleaned)
    if tail_hold:
        cleaned = cleaned[:-tail_hold]
    return cleaned
