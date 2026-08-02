from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    BARE_INVOKE_CHILD_OPEN_RE,
    BARE_INVOKE_CHILD_RE,
    INVOKE_DIRECT_CHILD_OPEN_RE,
    INVOKE_DIRECT_CHILD_RE,
    INVOKE_DIRECT_CHILD_SKIP,
    PARAM_CLOSE_BARE,
    PARAM_CLOSE_ENTML,
    PARAM_OPEN_PATTERN,
    extract_attr_value,
    extract_parameter_type_attr,
    find_valid_parameter_close,
    invoke_structural_gap_text,
    normalize_entml_name,
    parameter_close_at,
    split_mangled_json_param_tail,
    synthetic_close_invoke_body,
)
from echotools.exec.fncall.protocols.entml_schema import (
    coerce_entml_parameter_value,
    effective_entml_param_json_type,
)

_PARAM_OPEN_RE = re.compile(rf"{PARAM_OPEN_PATTERN}([^>]*)>", re.IGNORECASE)
_PARAM_CLOSE = PARAM_CLOSE_ENTML
_PARAMETERS_OPEN = "<entml:parameters>"
_PARAMETERS_CLOSE = "</entml:parameters>"
_INVOKE_CLOSE = "</entml:invoke>"
_INVOKE_OPEN_PREFIX = "<entml:invoke"


def _strip_incomplete_markup_suffix(value: str) -> str:
    lt = value.rfind("<")
    if lt < 0:
        return value
    tail = value[lt:]
    for tag in (_PARAM_CLOSE, PARAM_CLOSE_BARE, _PARAMETERS_CLOSE, _INVOKE_CLOSE):
        if tag.startswith(tail) and tail != tag:
            return value[:lt]
    return value


def _strip_incomplete_child_close_suffix(value: str, key: str) -> str:
    """流式未闭合 bare/direct 子标签：去掉尾部尚未收齐的 ``</...>``。"""
    value = _strip_incomplete_markup_suffix(value)
    lt = value.rfind("<")
    if lt < 0:
        return value
    tail = value[lt:]
    for close in (f"</entml:{key}>", f"</{key}>"):
        if close.startswith(tail) and tail != close:
            return value[:lt]
    return value


def split_invoke_open(
    buffer: str,
    *,
    known_names: Optional[Set[str]] = None,
) -> Optional[Tuple[str, int]]:
    """返回当前正在流式写入的 invoke（最后一个有效开标签）。"""
    search_from = 0
    prefix_len = len(_INVOKE_OPEN_PREFIX)
    last: Optional[Tuple[str, int]] = None
    while True:
        pos = buffer.find(_INVOKE_OPEN_PREFIX, search_from)
        if pos < 0:
            break
        from echotools.exec.fncall.protocols.entml_patterns import (
            entml_invoke_open_is_actionable,
        )

        if not entml_invoke_open_is_actionable(buffer, pos, known_names=known_names):
            gt = buffer.find(">", pos + prefix_len)
            search_from = (gt + 1) if gt >= 0 else (pos + prefix_len)
            continue
        gt = buffer.find(">", pos + prefix_len)
        if gt < 0:
            break
        attrs = buffer[pos + prefix_len : gt]
        name = extract_attr_value(attrs, "name")
        if name and normalize_entml_name(name):
            last = (normalize_entml_name(name), gt + 1)
        search_from = gt + 1
    return last


def _json_string_body(value: str) -> str:
    """JSON 字符串内部片段（不含外围引号）。"""
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _effective_param_type(
    value: str,
    pschema: Optional[Dict[str, Any]],
    type_hint: Optional[str],
) -> str:
    return effective_entml_param_json_type(value, pschema, type_hint)


def _synthetic_close_body(inner: str) -> str:
    """兼容旧名；委托 ``synthetic_close_invoke_body``。"""
    return synthetic_close_invoke_body(inner)


def _final_invoke_arguments_json(
    body: str,
    *,
    tool_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
    force_close: bool = False,
) -> str:
    """与批量 parse_invoke_args 完全一致的可解析 JSON。"""
    from echotools.exec.fncall.protocols.entml_tool.invoke import parse_invoke_args

    invoke_closed = _INVOKE_CLOSE in body
    inner = body[: body.index(_INVOKE_CLOSE)] if invoke_closed else body
    parse_body = synthetic_close_invoke_body(inner)
    args = parse_invoke_args(parse_body, tool_name, schema_index)
    return json.dumps(args, ensure_ascii=False)


def _streaming_string_value(raw: str, *, is_complete: bool) -> str:
    """流式 string 参数：保留模型原文；未完成时仅去掉尾部未收齐的标签前缀。"""
    if is_complete:
        return raw
    return _strip_incomplete_markup_suffix(raw)


def _parameter_json_fragment(
    value: str,
    is_complete: bool,
    param_type: str,
    pschema: Optional[Dict[str, Any]],
    type_hint: Optional[str],
) -> Optional[str]:
    """未完成 invoke 时，生成与 batch coercion 一致的参数 JSON 片段。

    返回 ``None`` 表示该参数尚未完成且不应出现在 snapshot（array/object）。
    """
    if is_complete:
        coerced = coerce_entml_parameter_value(
            value,
            pschema or None,
            type_hint=type_hint,
        )
        return json.dumps(coerced, ensure_ascii=False)
    if param_type in ("array", "object"):
        return None
    if param_type in ("integer", "number", "boolean"):
        return value
    streaming_val = _streaming_string_value(value, is_complete=is_complete)
    return f'"{_json_string_body(streaming_val)}'


def _resolve_parameter_close(body: str, val_start: int) -> int:
    """定位 parameter 闭合下标；流式 buffer 末尾的 bare ``</parameter>`` 亦视为已闭合。"""
    close = find_valid_parameter_close(body, val_start, allow_end=False)
    if close >= 0:
        return close
    close_end = find_valid_parameter_close(body, val_start, allow_end=True)
    if close_end < 0:
        return -1
    after = body[close_end + parameter_close_at(body, close_end) :]
    if not after.strip() and body.startswith(PARAM_CLOSE_BARE, close_end):
        return close_end
    return -1


def _incomplete_parameter_raw(body: str, val_start: int) -> str:
    """流式未闭合 parameter 的原始值（不含尚未确认的尾部结构闭合 token）。"""
    tail = body[val_start:]
    close = _resolve_parameter_close(body, val_start)
    if close >= 0:
        return body[val_start:close]
    for token in (_PARAM_CLOSE, PARAM_CLOSE_BARE):
        idx = tail.rfind(token)
        if idx >= 0:
            after = tail[idx + len(token) :]
            if not after.strip():
                return tail[:idx]
    return _strip_incomplete_markup_suffix(tail)


def _parse_bare_invoke_entries(body: str) -> List[Tuple[str, str, bool, Optional[str]]]:
    """返回 [(key, value, is_complete, type_hint), ...]（按 body 内出现顺序）。"""
    if not body:
        return []
    tagged: List[Tuple[int, str, str, bool, Optional[str]]] = []
    for match in BARE_INVOKE_CHILD_RE.finditer(body):
        key = normalize_entml_name(match.group(1))
        if not key:
            continue
        tagged.append((match.start(), key, match.group(2) or "", True, None))
    for match in BARE_INVOKE_CHILD_OPEN_RE.finditer(body):
        key = normalize_entml_name(match.group(1))
        if not key:
            continue
        close = f"</entml:{key}>"
        tail = match.group(2) or ""
        if close in tail:
            continue
        tail = _strip_incomplete_child_close_suffix(tail, key)
        tagged.append((match.start(), key, tail, False, None))
    tagged.sort(key=lambda item: item[0])
    seen: set[str] = set()
    entries: List[Tuple[str, str, bool, Optional[str]]] = []
    for _pos, key, value, is_complete, type_hint in tagged:
        if key in seen:
            continue
        seen.add(key)
        entries.append((key, value, is_complete, type_hint))
    return entries


def _parse_direct_child_entries(body: str) -> List[Tuple[str, str, bool, Optional[str]]]:
    """返回 [(key, value, is_complete, type_hint), ...]（直接子元素标签）。"""
    if not body:
        return []
    gap_text = invoke_structural_gap_text(body)
    tagged: List[Tuple[int, str, str, bool, Optional[str]]] = []
    for match in INVOKE_DIRECT_CHILD_RE.finditer(gap_text):
        key = normalize_entml_name(match.group(1))
        if not key or key.lower() in INVOKE_DIRECT_CHILD_SKIP:
            continue
        tagged.append((match.start(), key, match.group(2) or "", True, None))
    for match in INVOKE_DIRECT_CHILD_OPEN_RE.finditer(gap_text):
        key = normalize_entml_name(match.group(1))
        if not key or key.lower() in INVOKE_DIRECT_CHILD_SKIP:
            continue
        close = f"</{key}>"
        tail = match.group(2) or ""
        if close in tail:
            continue
        tail = _strip_incomplete_child_close_suffix(tail, key)
        tagged.append((match.start(), key, tail, False, None))
    tagged.sort(key=lambda item: item[0])
    seen: set[str] = set()
    entries: List[Tuple[str, str, bool, Optional[str]]] = []
    for _pos, key, value, is_complete, type_hint in tagged:
        if key in seen:
            continue
        seen.add(key)
        entries.append((key, value, is_complete, type_hint))
    return entries


def _parse_parameter_entries(body: str) -> List[Tuple[str, str, bool, Optional[str]]]:
    """返回 [(key, value, is_complete, type_hint), ...]。"""
    if not body:
        return []
    entries: List[Tuple[str, str, bool, Optional[str]]] = []
    i = 0
    while i < len(body):
        match = _PARAM_OPEN_RE.search(body, i)
        if not match:
            break
        attrs = match.group(1) or ""
        pname = extract_attr_value(attrs, "name")
        if not pname:
            i = match.end()
            continue
        key = normalize_entml_name(pname)
        type_hint = extract_parameter_type_attr(attrs)
        val_start = match.end()
        close = _resolve_parameter_close(body, val_start)
        if close < 0:
            raw = _incomplete_parameter_raw(body, val_start)
            raw, extra = split_mangled_json_param_tail(raw, param_name=key)
            entries.append(
                (
                    key,
                    raw,
                    False,
                    type_hint,
                )
            )
            for extra_key, extra_val in extra.items():
                entries.append((extra_key, str(extra_val), True, None))
            break
        raw = body[val_start:close]
        raw, extra = split_mangled_json_param_tail(raw, param_name=key)
        entries.append((key, raw, True, type_hint))
        for extra_key, extra_val in extra.items():
            entries.append((extra_key, str(extra_val), True, None))
        i = close + parameter_close_at(body, close)
    return entries
