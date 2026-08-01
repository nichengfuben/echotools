from __future__ import annotations

import re
from typing import Optional, Set

from .invoke import _strip_orphan_invoke_tags, _strip_orphan_non_invoke_tool_tags
from .params import strip_actionable_entml_invoke_blocks
from .regex import (
    _EMPTY_FENCE_RE,
    _FENCE_ONLY_LINE_RE,
    _TOOL_WRAPPER_PAIR_RE,
)


def strip_tool_entml_residue(
    content: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> str:
    """剥离工具相关 entml 标签残留，保留 thinking 与非工具 prose 提及。"""
    if not content:
        return content
    cleaned = _TOOL_WRAPPER_PAIR_RE.sub("", content)
    cleaned = strip_actionable_entml_invoke_blocks(cleaned, known_names=known_names)
    cleaned = _strip_orphan_invoke_tags(cleaned, known_names=known_names)
    cleaned = _strip_orphan_non_invoke_tool_tags(cleaned)
    cleaned = _EMPTY_FENCE_RE.sub("", cleaned)
    cleaned = _FENCE_ONLY_LINE_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
