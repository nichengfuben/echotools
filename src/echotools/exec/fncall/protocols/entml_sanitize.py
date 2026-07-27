from __future__ import annotations

import re

# 仅按 entml: 前缀剥离标签，不区分具体标签名。
_ENTML_PAIR_RE = re.compile(
    r"<entml:[a-zA-Z_][\w]*\b[^>]*>.*?</entml:[a-zA-Z_][\w]*>",
    re.DOTALL,
)
_ENTML_SELF_CLOSING_RE = re.compile(r"<entml:[a-zA-Z_][\w]*\b[^>]*/>", re.DOTALL)
_ENTML_ORPHAN_CLOSE_RE = re.compile(r"</entml:[a-zA-Z_][\w]*>", re.DOTALL)
_ENTML_ORPHAN_OPEN_RE = re.compile(r"<entml:[a-zA-Z_][\w]*\b[^>]*>", re.DOTALL)


def strip_entml_from_content(content: str) -> str:
    """从 user 消息正文剥离所有 entml:* 标签及残留开闭标签。"""
    if not content:
        return content
    cleaned = content
    cleaned = _ENTML_PAIR_RE.sub("", cleaned)
    cleaned = _ENTML_SELF_CLOSING_RE.sub("", cleaned)
    cleaned = _ENTML_ORPHAN_CLOSE_RE.sub("", cleaned)
    cleaned = _ENTML_ORPHAN_OPEN_RE.sub("", cleaned)
    return cleaned.strip()
