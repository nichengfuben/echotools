from __future__ import annotations

import json
from typing import Any, Dict, Optional

from echotools.exec.fncall.shared.coercion import _coerce_param_value

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


def _schema_from_type_hint(type_hint: str) -> Optional[Dict[str, Any]]:
    json_type = _TYPE_HINT_TO_JSON_TYPE.get((type_hint or "").strip().lower())
    if not json_type:
        return None
    schema: Dict[str, Any] = {"type": json_type}
    if json_type == "array":
        schema["items"] = {}
    return schema


def coerce_entml_parameter_value(
    raw: str,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Any:
    """将 entml 参数文本按 schema、type 属性或默认 str 规则转为 Python 值。"""
    if schema:
        return _coerce_param_value(raw, schema)

    hint_schema = _schema_from_type_hint(type_hint) if type_hint else None
    if hint_schema:
        return _coerce_param_value(raw, hint_schema)

    stripped = (raw or "").strip()
    if not stripped:
        return ""

    if stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped

    return stripped


def coerce_entml_arguments(
    args: Dict[str, Any],
    func_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Dict[str, Any]:
    """对已解析参数字典按工具 schema 做逐项类型转换。"""
    if not schema_index or not func_name:
        return args
    func_schema = schema_index.get(func_name) or {}
    if not func_schema:
        return args

    out: Dict[str, Any] = {}
    for key, value in args.items():
        pschema = func_schema.get(key) or {}
        if isinstance(value, str) and pschema:
            out[key] = coerce_entml_parameter_value(value, pschema)
        else:
            out[key] = value
    return out
