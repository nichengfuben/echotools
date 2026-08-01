from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .params import extract_attr_value, normalize_entml_name
from .regex import _INVOKE_CLOSE, _INVOKE_OPEN_PREFIX


def is_placeholder_invoke_name(name: str) -> bool:
    """提示词占位符（如 ``$FUNCTION_NAME``）不算真实工具调用。"""
    n = (name or "").strip()
    return not n or "$" in n


def resolve_known_tool_names(
    tools: Optional[List[Dict[str, Any]]] = None,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> Optional[Set[str]]:
    """从 tools / schema_index 解析已知工具名；无约束时返回 ``None``。"""
    if schema_index:
        return {normalize_entml_name(str(k)) for k in schema_index.keys()}
    names: Set[str] = set()
    for tool in tools or []:
        fn = tool.get("function") or {}
        name = fn.get("name")
        if name:
            names.add(normalize_entml_name(str(name)))
    return names if names else None


def _name_is_known(name: str, known_names: Optional[Set[str]]) -> bool:
    if known_names is None:
        return True
    if not known_names:
        return False
    return normalize_entml_name(name) in known_names


def entml_invoke_open_is_actionable(
    buffer: str,
    pos: int,
    *,
    known_names: Optional[Set[str]] = None,
) -> bool:
    """``pos`` 处 ``<entml:invoke`` 是否为已闭合、含真实 name 且（若提供）在已知工具表内的开标签。"""
    if pos < 0 or not buffer.startswith(_INVOKE_OPEN_PREFIX, pos):
        return False
    gt = buffer.find(">", pos + len(_INVOKE_OPEN_PREFIX))
    if gt < 0:
        return False
    attrs = buffer[pos + len(_INVOKE_OPEN_PREFIX) : gt]
    name = extract_attr_value(attrs, "name")
    if not name:
        return False
    name = normalize_entml_name(name)
    if not name or is_placeholder_invoke_name(name):
        return False
    return _name_is_known(name, known_names)


def entml_invoke_open_may_be_streaming(
    buffer: str,
    pos: int,
    *,
    known_names: Optional[Set[str]] = None,
) -> bool:
    """``pos`` 处 ``<entml:invoke`` 是否仍可能长成可解析工具开标签（非 prose 提及）。"""
    if pos < 0 or not buffer.startswith(_INVOKE_OPEN_PREFIX, pos):
        return False
    gt = buffer.find(">", pos + len(_INVOKE_OPEN_PREFIX))
    if gt < 0:
        return True
    return entml_invoke_open_is_actionable(buffer, pos, known_names=known_names)


def find_actionable_entml_invoke_open(
    buffer: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> int:
    """返回首个可解析 ``<entml:invoke`` 起始下标；否则 ``-1``。"""
    if not buffer:
        return -1
    search_from = 0
    prefix_len = len(_INVOKE_OPEN_PREFIX)
    while search_from < len(buffer):
        pos = buffer.find(_INVOKE_OPEN_PREFIX, search_from)
        if pos < 0:
            return -1
        if entml_invoke_open_is_actionable(buffer, pos, known_names=known_names):
            return pos
        gt = buffer.find(">", pos + prefix_len)
        search_from = (gt + 1) if gt >= 0 else (pos + prefix_len)
    return -1


def _actionable_invoke_open_before_close(
    content: str,
    close_pos: int,
    *,
    known_names: Optional[Set[str]] = None,
) -> bool:
    """``close_pos`` 处的 ``</entml:invoke>`` 是否闭合带真实 name 的开标签。"""
    search = close_pos - 1
    while search >= 0:
        pos = content.rfind(_INVOKE_OPEN_PREFIX, 0, search + 1)
        if pos < 0:
            return False
        if entml_invoke_open_is_actionable(content, pos, known_names=known_names):
            gt = content.find(">", pos)
            if gt < 0 or gt >= close_pos:
                search = pos - 1
                continue
            inner_close = content.find(_INVOKE_CLOSE, gt + 1, close_pos)
            if inner_close < 0:
                return True
            search = pos - 1
            continue
        search = pos - 1
    return False


def _invoke_close_should_strip(
    content: str,
    close_pos: int,
    *,
    known_names: Optional[Set[str]] = None,
) -> bool:
    """是否应剥离 ``</entml:invoke>``（孤儿噪声或真实工具块残留）。"""
    if _actionable_invoke_open_before_close(content, close_pos, known_names=known_names):
        return True
    open_pos = content.rfind(_INVOKE_OPEN_PREFIX, 0, close_pos)
    if open_pos < 0:
        return True
    return entml_invoke_open_is_actionable(content, open_pos, known_names=known_names)


def iter_actionable_entml_invoke_blocks(
    text: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> Iterator[Tuple[int, int, str, str]]:
    """迭代含真实 ``name`` 的完整 ``<entml:invoke>…</entml:invoke>`` 块。"""
    if not text:
        return
    search_from = 0
    prefix_len = len(_INVOKE_OPEN_PREFIX)
    close_len = len(_INVOKE_CLOSE)
    while search_from < len(text):
        pos = text.find(_INVOKE_OPEN_PREFIX, search_from)
        if pos < 0:
            break
        if not entml_invoke_open_is_actionable(text, pos, known_names=known_names):
            gt = text.find(">", pos + prefix_len)
            search_from = (gt + 1) if gt >= 0 else (pos + prefix_len)
            continue
        gt = text.find(">", pos + prefix_len)
        if gt < 0:
            break
        close = text.find(_INVOKE_CLOSE, gt + 1)
        if close < 0:
            break
        attrs = text[pos + prefix_len : gt]
        body = text[gt + 1 : close]
        yield pos, close + close_len, attrs, body
        search_from = close + close_len


def _strip_orphan_invoke_tags(
    content: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> str:
    """仅剥离带真实 name 的 invoke 孤儿标签；保留 prose 中的 ``<entml:invoke>`` 提及。"""
    pattern = re.compile(r"</?entml:invoke\b[^>]*/?>", re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if tag.startswith("</"):
            if _invoke_close_should_strip(content, match.start(), known_names=known_names):
                return ""
            return tag
        if entml_invoke_open_is_actionable(content, match.start(), known_names=known_names):
            return ""
        return tag

    return pattern.sub(repl, content)


def _strip_orphan_non_invoke_tool_tags(content: str) -> str:
    return re.sub(
        r"</?entml:(?:function_calls|parameter|parameters)\b[^>]*/?>",
        "",
        content,
        flags=re.DOTALL,
    )
