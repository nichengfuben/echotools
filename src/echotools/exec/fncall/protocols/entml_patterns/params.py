from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..entml_tool.values import coerce_entml_parameter_value
from .regex import (
    _ATTR_NAME_RE,
    _FOLLOWER_PREFIXES,
    _PARAM_OPEN_TAG_RE,
    _PARAM_TYPE_ATTR_RE,
    PARAM_CLOSE_BARE,
    PARAM_CLOSE_ENTML,
    SUB_TAG_RE,
)


def parameter_close_at(body: str, close_pos: int) -> int:
    """``close_pos`` 处 parameter 闭合标签的字节长度（entml 或 bare）。"""
    if body.startswith(PARAM_CLOSE_ENTML, close_pos):
        return len(PARAM_CLOSE_ENTML)
    if body.startswith(PARAM_CLOSE_BARE, close_pos):
        if close_pos >= len("</entml:") and body.startswith(
            PARAM_CLOSE_ENTML, close_pos - len("</entml:")
        ):
            return 0
        return len(PARAM_CLOSE_BARE)
    return 0


def _parameter_close_follower_ok(after: str, *, allow_end: bool) -> bool:
    stripped = after.lstrip()
    if not stripped:
        return allow_end
    for prefix in _FOLLOWER_PREFIXES:
        if stripped.startswith(prefix) or prefix.startswith(stripped):
            return True
    return False


def synthetic_close_invoke_body(inner: str) -> str:
    """为 force_close / invoke 已闭合但未闭合的 parameter 补齐结构闭合标签。"""
    if not inner:
        return inner
    closed = inner
    if "<entml:parameters>" in closed and "</entml:parameters>" not in closed:
        closed = closed + "</entml:parameters>"
    matches = list(_PARAM_OPEN_TAG_RE.finditer(closed))
    if matches:
        last = matches[-1]
        after = closed[last.end() :]
        open_snip = closed[last.start() : last.end()].lower()
        if open_snip.startswith("<parameter") and not open_snip.startswith("<entml:"):
            need = PARAM_CLOSE_BARE
        else:
            need = PARAM_CLOSE_ENTML
        if need not in after and find_valid_parameter_close(closed, last.end(), allow_end=True) < 0:
            closed = closed + need
    return closed


def find_valid_parameter_close(body: str, search_from: int = 0, *, allow_end: bool = True) -> int:
    """返回 parameter 闭合标签在 ``body`` 中的起始下标；忽略参数值内的假闭合。"""
    pos = search_from
    while pos < len(body):
        next_entml = body.find(PARAM_CLOSE_ENTML, pos)
        next_bare = body.find(PARAM_CLOSE_BARE, pos)
        if next_entml < 0 and next_bare < 0:
            return -1
        candidates = []
        if next_entml >= 0:
            candidates.append(next_entml)
        if next_bare >= 0 and parameter_close_at(body, next_bare) > 0:
            candidates.append(next_bare)
        if not candidates:
            pos = min(x for x in (next_entml, next_bare) if x >= 0) + 1
            continue
        close = min(candidates)
        close_len = parameter_close_at(body, close)
        after = body[close + close_len :]
        if _parameter_close_follower_ok(after, allow_end=allow_end):
            return close
        pos = close + 1
    return -1


def parameter_value_spans(body: str) -> List[Tuple[int, int]]:
    """``<entml:parameter>`` 值区间（含未闭合 parameter 的 growing tail）。"""
    if not body:
        return []
    spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(body):
        match = _PARAM_OPEN_TAG_RE.search(body, i)
        if not match:
            break
        val_start = match.end()
        close = find_valid_parameter_close(body, val_start, allow_end=True)
        if close < 0:
            spans.append((val_start, len(body)))
            break
        spans.append((val_start, close))
        i = close + parameter_close_at(body, close)
    return spans


def parameter_block_spans(body: str) -> List[Tuple[int, int]]:
    """完整 ``<entml:parameter …>…</entml:parameter>`` 块（含开闭标签）。"""
    if not body:
        return []
    spans: List[Tuple[int, int]] = []
    i = 0
    while i < len(body):
        match = _PARAM_OPEN_TAG_RE.search(body, i)
        if not match:
            break
        block_start = match.start()
        val_start = match.end()
        close = find_valid_parameter_close(body, val_start, allow_end=True)
        if close < 0:
            spans.append((block_start, len(body)))
            break
        block_end = close + parameter_close_at(body, close)
        spans.append((block_start, block_end))
        i = block_end
    return spans


def invoke_structural_gaps(body: str) -> List[Tuple[int, int]]:
    """invoke 体内可承载备用参数语法的区间（parameter 块之外）。"""
    if not body:
        return []
    blocks = parameter_block_spans(body)
    if not blocks:
        return [(0, len(body))]
    gaps: List[Tuple[int, int]] = []
    pos = 0
    for start, end in blocks:
        if pos < start:
            gaps.append((pos, start))
        pos = end
    if pos < len(body):
        gaps.append((pos, len(body)))
    return gaps


def invoke_structural_gap_text(body: str) -> str:
    """parameter 块视为不透明 payload 后，invoke 体剩余可解析文本。"""
    return "".join(body[s:e] for s, e in invoke_structural_gaps(body))


def inside_parameter_value(pos: int, spans: List[Tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def extract_attr_value(attrs: str, attr_name: str = "name") -> Optional[str]:
    """从标签属性串中提取 name/type 等（支持单双引号）。"""
    if not attrs:
        return None
    if attr_name == "name":
        match = _ATTR_NAME_RE.search(attrs)
    elif attr_name == "type":
        match = _PARAM_TYPE_ATTR_RE.search(attrs)
    else:
        pattern = re.compile(
            rf"""\b{re.escape(attr_name)}\s*=\s*(?P<q>["'])(?P<v>.*?)(?P=q)"""
        )
        match = pattern.search(attrs)
    if not match:
        return None
    return match.group("v").strip()


def normalize_entml_name(name: str) -> str:
    """还原 markdown 转义下划线等常见名称噪声。"""
    if not name:
        return ""
    return name.replace("\\_", "_").replace("\\-", "-").strip()


def extract_parameter_type_attr(attrs: str) -> Optional[str]:
    """从 parameter 开标签属性中提取 type=\"...\"。"""
    return extract_attr_value(attrs or "", "type")


def parse_sub_tags(
    content: str,
    schema_index: Optional[Dict[str, Any]] = None,
    func_name: str = "",
) -> Dict[str, Any]:
    """解析 <entml:parameters> 内的子标签，返回参数字典。"""
    args: Dict[str, Any] = {}
    for m in SUB_TAG_RE.finditer(content):
        pname = m.group(1).strip()
        pval = m.group(2).strip()
        pschema = schema_index.get(func_name, {}).get(pname, {}) if schema_index else {}
        args[pname] = coerce_entml_parameter_value(pval, pschema or None)
    return args


def strip_actionable_entml_invoke_blocks(
    text: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> str:
    """仅剥离含真实 ``name`` 的 invoke 块；保留 prose ``<entml:invoke>`` 提及。"""
    from .invoke import iter_actionable_entml_invoke_blocks

    if not text:
        return text
    parts: List[str] = []
    last = 0
    for start, end, _attrs, _body in iter_actionable_entml_invoke_blocks(
        text, known_names=known_names
    ):
        parts.append(text[last:start])
        last = end
    parts.append(text[last:])
    return "".join(parts)
