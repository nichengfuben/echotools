from __future__ import annotations

import json
from typing import Any, Dict, Optional

from echotools.exec.fncall.shared.coercion import _coerce_param_value


def coerce_entml_parameter_value(
    raw: str,
    schema: Optional[Dict[str, Any]] = None,
) -> Any:
    """将 entml 参数文本按 schema（若有）或边界规则转为 Python 值。"""
    if schema:
        return _coerce_param_value(raw, schema)

    stripped = (raw or "").strip()
    if not stripped:
        return ""

    if stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw

    lowered = stripped.lower()
    if lowered == "null":
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    if stripped.isdigit() or (
        stripped.startswith("-") and stripped[1:].isdigit()
    ):
        try:
            return int(stripped)
        except ValueError:
            pass

    try:
        if any(ch in stripped for ch in ".eE"):
            fval = float(stripped)
            if fval.is_integer() and "." not in stripped and "e" not in lowered:
                return int(fval)
            return fval
    except ValueError:
        pass

    return raw


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
