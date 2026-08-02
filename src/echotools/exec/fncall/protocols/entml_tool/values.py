from __future__ import annotations

import json
from typing import Any, Dict, Optional, Sequence

from echotools.exec.fncall.shared.coercion import (
    _coerce_param_value,
    _resolve_effective_type,
)
from echotools.exec.fncall.protocols.entml_schema.validate import (
    assert_valid_tool_arguments,
)

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


def resolve_entml_parameter_schema(
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """解析参数 effective schema：模型 ``type`` 属性优先，否则用工具 schema。"""
    hint_schema = _schema_from_type_hint(type_hint) if type_hint else None
    if hint_schema:
        return hint_schema
    if schema:
        return schema
    return None


def coerce_entml_parameter_value(
    raw: str,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Any:
    """将 entml 参数文本转为 Python 值。

    类型优先级：parameter 上的 ``type`` 属性 > 工具 JSON Schema > 默认 string。
    """
    effective = resolve_entml_parameter_schema(schema, type_hint)
    if effective:
        return _coerce_param_value(raw, effective)

    if raw is None or raw == "":
        return ""

    if raw.lstrip().startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    return raw


def effective_entml_param_json_type(
    value: str,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> str:
    """流式 partial_json 与 batch 共用：模型 type 优先，否则 schema，再否则按值推断。"""
    effective = resolve_entml_parameter_schema(schema, type_hint)
    if effective:
        resolved = _resolve_effective_type(effective)
        if resolved:
            return resolved
    stripped = (value or "").lstrip()
    if stripped.startswith("["):
        return "array"
    if stripped.startswith("{"):
        return "object"
    return "string"


def _coerce_entml_arg_value(
    value: Any,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Any:
    """将已解析的 Python 值再按 type_hint / schema 归一（与 batch 单参路径一致）。"""
    if isinstance(value, str):
        return coerce_entml_parameter_value(value, schema, type_hint=type_hint)
    if isinstance(value, (dict, list)):
        return coerce_entml_parameter_value(
            json.dumps(value, ensure_ascii=False),
            schema,
            type_hint=type_hint,
        )
    if value is None:
        return coerce_entml_parameter_value("", schema, type_hint=type_hint)
    return coerce_entml_parameter_value(str(value), schema, type_hint=type_hint)


def coerce_entml_arguments(
    args: Dict[str, Any],
    func_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
    *,
    strict: bool = False,
    required: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """对已解析参数字典按工具 schema 做逐项类型转换，可选 strict 校验。"""
    if not schema_index or not func_name:
        return args
    func_schema = schema_index.get(func_name) or {}
    if not func_schema:
        return args

    out: Dict[str, Any] = {}
    for key, value in args.items():
        pschema = func_schema.get(key) or {}
        if pschema:
            out[key] = _coerce_entml_arg_value(value, pschema)
        else:
            out[key] = value
    if strict:
        assert_valid_tool_arguments(
            out, func_name, schema_index, required=required
        )
    return out
