from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .entml_patterns import (
    extract_attr_value,
    extract_parameter_type_attr,
    normalize_entml_name,
)
from .entml_values import coerce_entml_parameter_value

_PARAM_OPEN_RE = re.compile(r"<entml:parameter\b([^>]*)>", re.IGNORECASE)
_PARAM_CLOSE = "</entml:parameter>"
_PARAMETERS_OPEN = "<entml:parameters>"
_PARAMETERS_CLOSE = "</entml:parameters>"
_INVOKE_CLOSE = "</entml:invoke>"
_INVOKE_OPEN_PREFIX = "<entml:invoke"

_TYPE_HINT_TO_JSON_TYPE = {
    "str": "string",
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "double": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "array": "array",
    "list": "array",
    "object": "object",
    "dict": "object",
}


def _strip_incomplete_markup_suffix(value: str) -> str:
    lt = value.rfind("<")
    if lt < 0:
        return value
    tail = value[lt:]
    for tag in (_PARAM_CLOSE, _PARAMETERS_CLOSE, _INVOKE_CLOSE):
        if tag.startswith(tail) and tail != tag:
            return value[:lt]
    return value


def split_invoke_open(buffer: str) -> Optional[Tuple[str, int]]:
    """返回当前正在流式写入的 invoke（最后一个有效开标签）。"""
    search_from = 0
    prefix_len = len(_INVOKE_OPEN_PREFIX)
    last: Optional[Tuple[str, int]] = None
    while True:
        pos = buffer.find(_INVOKE_OPEN_PREFIX, search_from)
        if pos < 0:
            break
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
    if type_hint:
        mapped = _TYPE_HINT_TO_JSON_TYPE.get(type_hint.strip().lower())
        if mapped:
            return mapped
    if pschema and pschema.get("type"):
        return str(pschema["type"])
    stripped = (value or "").lstrip()
    if stripped.startswith("["):
        return "array"
    if stripped.startswith("{"):
        return "object"
    return "string"


def _synthetic_close_body(inner: str) -> str:
    """为 force_close 补齐未闭合的 parameter / parameters 标签。"""
    if _INVOKE_CLOSE in inner:
        inner = inner[: inner.index(_INVOKE_CLOSE)]
    closed = inner
    if _PARAMETERS_OPEN in closed and _PARAMETERS_CLOSE not in closed:
        closed = closed + _PARAMETERS_CLOSE
    matches = list(_PARAM_OPEN_RE.finditer(closed))
    if matches:
        last = matches[-1]
        after = closed[last.end() :]
        if _PARAM_CLOSE not in after:
            closed = closed + _PARAM_CLOSE
    return closed


def _final_invoke_arguments_json(
    body: str,
    *,
    tool_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
    force_close: bool = False,
) -> str:
    """与批量 parse_invoke_args 完全一致的可解析 JSON。"""
    from .entml_invoke import parse_invoke_args

    invoke_closed = _INVOKE_CLOSE in body
    inner = body[: body.index(_INVOKE_CLOSE)] if invoke_closed else body
    parse_body = inner if invoke_closed else _synthetic_close_body(inner)
    args = parse_invoke_args(parse_body, tool_name, schema_index)
    return json.dumps(args, ensure_ascii=False)


def _streaming_string_value(raw: str, *, is_complete: bool) -> str:
    """与 ``parse_invoke_args`` 的 ``strip()`` 对齐，并避免 XML 换行导致非单调前缀。"""
    if is_complete:
        return raw.strip()
    return raw.lstrip().rstrip("\r\n")


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
        close = body.find(_PARAM_CLOSE, val_start)
        if close < 0:
            entries.append(
                (
                    key,
                    _strip_incomplete_markup_suffix(body[val_start:]),
                    False,
                    type_hint,
                )
            )
            break
        entries.append((key, body[val_start:close].strip(), True, type_hint))
        i = close + len(_PARAM_CLOSE)
    return entries


def _parameters_block_snapshot(
    inner: str,
    *,
    tool_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Optional[str]:
    """处理 ``<entml:parameters>`` 整包参数（流式前缀或完整 JSON）。"""
    open_pos = inner.find(_PARAMETERS_OPEN)
    if open_pos < 0:
        return None
    content_start = open_pos + len(_PARAMETERS_OPEN)
    close_pos = inner.find(_PARAMETERS_CLOSE, content_start)
    if close_pos >= 0:
        closed_body = inner[: close_pos + len(_PARAMETERS_CLOSE)]
        from .entml_invoke import parse_invoke_args

        args = parse_invoke_args(closed_body, tool_name, schema_index)
        return json.dumps(args, ensure_ascii=False)
    return ""


def build_streaming_json_snapshot(
    body: str,
    *,
    tool_name: str = "",
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    force_close: bool = False,
) -> str:
    """构造当前应已发出的 partial_json 累积串（可未完成）。

    invoke 闭合（或 force_close）时直接走 ``parse_invoke_args``，与批量解析一致。
    未完成时仅输出合法 JSON 前缀，且不在 ``</entml:invoke>`` 前闭合最外层 ``}``。
    """
    invoke_closed = _INVOKE_CLOSE in body
    inner = body[: body.index(_INVOKE_CLOSE)] if invoke_closed else body

    if invoke_closed or force_close:
        return _final_invoke_arguments_json(
            body,
            tool_name=tool_name,
            schema_index=schema_index,
            force_close=force_close,
        )

    params_snap = _parameters_block_snapshot(
        inner, tool_name=tool_name, schema_index=schema_index
    )
    if params_snap is not None:
        return params_snap

    entries = _parse_parameter_entries(inner)
    if not entries:
        return ""

    func_schema = (schema_index or {}).get(tool_name) or {}
    parts: List[str] = ["{"]
    for idx, (key, value, is_complete, type_hint) in enumerate(entries):
        if idx > 0:
            parts.append(", ")
        parts.append(json.dumps(key, ensure_ascii=False))
        parts.append(": ")
        pschema = func_schema.get(key) or {}
        param_type = _effective_param_type(value, pschema, type_hint)
        fragment = _parameter_json_fragment(
            value, is_complete, param_type, pschema, type_hint
        )
        if fragment is None:
            if idx == 0:
                return ""
            return "".join(parts)
        parts.append(fragment)
        if not is_complete:
            return "".join(parts)

    return "".join(parts)


def _parse_partial_parameter_body(body: str) -> Dict[str, Any]:
    obj: Dict[str, Any] = {}
    for key, value, is_complete, _type_hint in _parse_parameter_entries(
        body[: body.index(_INVOKE_CLOSE)] if _INVOKE_CLOSE in body else body
    ):
        if is_complete or value:
            obj[key] = value
    return obj


def encode_streaming_invoke_json(body: str) -> str:
    obj = _parse_partial_parameter_body(body)
    if not obj:
        return ""
    return json.dumps(obj, ensure_ascii=False)


class EntmlInvokeJsonStreamEncoder:
    """invoke 开标签之后，将 growing body 编码为可拼接的 partial_json 增量。"""

    def __init__(
        self,
        *,
        tool_name: str = "",
        schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        self._emitted = ""
        self._tool_name = tool_name
        self._schema_index = schema_index

    def set_tool_context(
        self,
        tool_name: str,
        schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        if tool_name != self._tool_name:
            self._emitted = ""
        self._tool_name = tool_name
        self._schema_index = schema_index

    def poll(self, body: str, *, force_close: bool = False) -> str:
        snapshot = build_streaming_json_snapshot(
            body,
            tool_name=self._tool_name,
            schema_index=self._schema_index,
            force_close=force_close,
        )
        if not snapshot:
            return ""
        if not snapshot.startswith(self._emitted):
            common = 0
            for a, b in zip(self._emitted, snapshot):
                if a != b:
                    break
                common += 1
            delta = snapshot[common:]
            self._emitted = snapshot
            return delta
        delta = snapshot[len(self._emitted) :]
        self._emitted = snapshot
        return delta

    def reset(self) -> None:
        self._emitted = ""
