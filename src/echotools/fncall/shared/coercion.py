"""Schema 感知参数类型转换。

从 src/core/tools.py 迁移（原 lines 116-510）。
所有协议共享此模块。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from echotools.logger.manager import get_logger

logger = get_logger(__name__)

_SCALAR_TYPES = frozenset({"string", "integer", "number", "boolean", "null"})
_CONTAINER_TYPES = frozenset({"array", "object"})


def _build_param_schema_index(
    tools: Optional[List[Dict[str, Any]]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """将工具列表构建为快速查找索引。

    返回结构::

        {
            "func_name": {
                "param_name": <JSON Schema dict>,
                ...
            },
            ...
        }
    """
    if not tools:
        return {}

    index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for tool in tools:
        fn: Dict[str, Any] = tool.get("function", tool)  # type: ignore[arg-type]
        name: str = fn.get("name") or ""
        if not name:
            continue
        props: Dict[str, Any] = (
            (fn.get("parameters") or {}).get("properties") or {}
        )
        index[name] = {
            pname: (pschema if isinstance(pschema, dict) else {})
            for pname, pschema in props.items()
        }
    return index


def _resolve_effective_type(schema: Dict[str, Any]) -> Optional[str]:
    """从 JSON Schema 中解析出有效的单一类型字符串。"""
    if not schema:
        return None

    raw_type = schema.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    if isinstance(raw_type, list):
        non_null = [t for t in raw_type if t != "null" and isinstance(t, str)]
        if non_null:
            return non_null[0]

    for combiner_key in ("anyOf", "oneOf"):
        combiner = schema.get(combiner_key)
        if not isinstance(combiner, list):
            continue
        for sub in combiner:
            if not isinstance(sub, dict):
                continue
            sub_type = sub.get("type")
            if isinstance(sub_type, str) and sub_type != "null":
                return sub_type

    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        first = enum_vals[0]
        if isinstance(first, bool):
            return "boolean"
        if isinstance(first, int):
            return "integer"
        if isinstance(first, float):
            return "number"
        if isinstance(first, str):
            return "string"
        if isinstance(first, list):
            return "array"
        if isinstance(first, dict):
            return "object"

    return None


def _coerce_to_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _coerce_to_integer(raw: str, parsed: Any) -> Any:
    if isinstance(parsed, bool):
        return int(parsed)
    if isinstance(parsed, int):
        return parsed
    if isinstance(parsed, float):
        if parsed.is_integer():
            return int(parsed)
        logger.debug("_coerce_to_integer: 浮点数 %r 不是整值，保留为 float", parsed)
        return parsed

    stripped = raw.strip()
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        fval = float(stripped)
        if fval.is_integer():
            return int(fval)
        logger.debug("_coerce_to_integer: %r 为非整浮点，保留为 float", stripped)
        return fval
    except ValueError:
        pass

    logger.debug("_coerce_to_integer: 无法转换 %r，原样返回", raw[:100])
    return parsed


def _coerce_to_number(raw: str, parsed: Any) -> Any:
    if isinstance(parsed, bool):
        return int(parsed)
    if isinstance(parsed, (int, float)):
        return parsed

    stripped = raw.strip()
    try:
        ival = int(stripped)
        return ival
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass

    logger.debug("_coerce_to_number: 无法转换 %r，原样返回", raw[:100])
    return parsed


def _coerce_to_boolean(raw: str, parsed: Any) -> Any:
    if isinstance(parsed, bool):
        return parsed
    if isinstance(parsed, int):
        return bool(parsed)

    normalized = raw.strip().lower()
    if normalized in ("true", "yes", "1", "on"):
        return True
    if normalized in ("false", "no", "0", "off"):
        return False

    logger.debug("_coerce_to_boolean: 无法识别布尔值 %r，原样返回", raw[:100])
    return parsed


def _coerce_to_array(raw: str, parsed: Any, item_schema: Dict[str, Any]) -> Any:
    result_list: Any = None

    if isinstance(parsed, list):
        result_list = parsed
    elif isinstance(parsed, str):
        try:
            candidate = json.loads(parsed)
            if isinstance(candidate, list):
                result_list = candidate
        except json.JSONDecodeError:
            pass
    elif isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("["):
            try:
                candidate = json.loads(stripped)
                if isinstance(candidate, list):
                    result_list = candidate
            except json.JSONDecodeError:
                pass

    if result_list is None:
        logger.debug("_coerce_to_array: 无法解析为列表，原样返回 %r", raw[:100])
        return parsed

    if item_schema:
        return [
            _coerce_param_value(
                json.dumps(item, ensure_ascii=False) if not isinstance(item, str) else item,
                item_schema,
            )
            for item in result_list
        ]
    return result_list


def _coerce_to_object(raw: str, parsed: Any, schema: Dict[str, Any]) -> Any:
    result_dict: Any = None

    if isinstance(parsed, dict):
        result_dict = parsed
    elif isinstance(parsed, str):
        try:
            candidate = json.loads(parsed)
            if isinstance(candidate, dict):
                result_dict = candidate
        except json.JSONDecodeError:
            pass
    elif isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                candidate = json.loads(stripped)
                if isinstance(candidate, dict):
                    result_dict = candidate
            except json.JSONDecodeError:
                pass

    if result_dict is None:
        logger.debug("_coerce_to_object: 无法解析为字典，原样返回 %r", raw[:100])
        return parsed

    sub_props: Dict[str, Any] = schema.get("properties") or {}
    if not sub_props:
        return result_dict

    coerced: Dict[str, Any] = {}
    for k, v in result_dict.items():
        field_schema = sub_props.get(k)
        if isinstance(field_schema, dict) and field_schema:
            v_raw = (
                v if isinstance(v, str)
                else json.dumps(v, ensure_ascii=False)
            )
            coerced[k] = _coerce_param_value(v_raw, field_schema)
        else:
            coerced[k] = v
    return coerced


def _coerce_param_value(raw: str, schema: Dict[str, Any]) -> Any:
    """根据 JSON Schema 对单个参数的原始字符串值做精确类型转换。"""
    stripped = raw.strip()
    try:
        parsed: Any = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        parsed = raw

    if not schema:
        return parsed

    effective_type = _resolve_effective_type(schema)

    if effective_type is None:
        return parsed

    if effective_type == "string":
        if isinstance(parsed, str):
            return parsed
        return _coerce_to_string(parsed)

    if effective_type == "integer":
        return _coerce_to_integer(stripped, parsed)

    if effective_type == "number":
        return _coerce_to_number(stripped, parsed)

    if effective_type == "boolean":
        return _coerce_to_boolean(stripped, parsed)

    if effective_type == "null":
        return None

    if effective_type == "array":
        item_schema: Dict[str, Any] = schema.get("items") or {}
        return _coerce_to_array(stripped, parsed, item_schema)

    if effective_type == "object":
        return _coerce_to_object(stripped, parsed, schema)

    logger.debug("_coerce_param_value: 未知类型 %r，退化为 json.loads 结果", effective_type)
    return parsed
