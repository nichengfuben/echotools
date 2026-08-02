"""JSON Schema 边界校验（coerce 之后）：enum、null union、基础类型匹配。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from echotools.exec.fncall.shared.coercion import is_null_literal, schema_allows_null

_SCALAR_CHECK = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


@dataclass(frozen=True)
class ParamValidationIssue:
    path: str
    message: str

    def to_llm_feedback(self) -> str:
        loc = self.path or "(root)"
        return f"Parameter validation failed at {loc}: {self.message}"


class ToolArgValidationError(Exception):
    """工具参数未通过 schema 校验（可回灌模型自修正）。"""

    def __init__(
        self,
        issues: Sequence[ParamValidationIssue],
        *,
        tool_name: str = "",
    ) -> None:
        self.tool_name = tool_name
        self.issues = list(issues)
        detail = "; ".join(i.message for i in self.issues)
        super().__init__(detail or "tool argument validation failed")

    def to_llm_feedback(self) -> str:
        lines = [i.to_llm_feedback() for i in self.issues]
        prefix = f"Tool {self.tool_name!r} arguments invalid." if self.tool_name else ""
        body = "\n".join(lines)
        return f"{prefix}\n{body}".strip() if prefix else body


def _enum_values(schema: Dict[str, Any]) -> Optional[List[Any]]:
    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        return list(enum_vals)
    return None


def _type_names(schema: Dict[str, Any]) -> List[str]:
    raw_type = schema.get("type")
    if isinstance(raw_type, str) and raw_type:
        return [raw_type]
    if isinstance(raw_type, list):
        return [t for t in raw_type if isinstance(t, str)]
    enum_vals = schema.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        first = enum_vals[0]
        if isinstance(first, bool):
            return ["boolean"]
        if isinstance(first, int):
            return ["integer"]
        if isinstance(first, float):
            return ["number"]
        if isinstance(first, str):
            return ["string"]
        if isinstance(first, list):
            return ["array"]
        if isinstance(first, dict):
            return ["object"]
    for combiner_key in ("anyOf", "oneOf"):
        combiner = schema.get(combiner_key)
        if not isinstance(combiner, list):
            continue
        names: List[str] = []
        for sub in combiner:
            if isinstance(sub, dict):
                names.extend(_type_names(sub))
        if names:
            return list(dict.fromkeys(names))
    return []


def _value_matches_types(value: Any, type_names: Sequence[str]) -> bool:
    if not type_names:
        return True
    if value is None:
        return "null" in type_names
    for name in type_names:
        if name == "null":
            continue
        checker = _SCALAR_CHECK.get(name)
        if checker and checker(value):
            return True
    return False


def validate_param_value(
    value: Any,
    schema: Dict[str, Any],
    *,
    path: str = "",
) -> List[ParamValidationIssue]:
    if not schema:
        return []
    issues: List[ParamValidationIssue] = []
    enum_vals = _enum_values(schema)
    if enum_vals is not None and value not in enum_vals:
        issues.append(
            ParamValidationIssue(
                path,
                f"value {value!r} is not one of {enum_vals!r}",
            )
        )
    type_names = _type_names(schema)
    if type_names and not _value_matches_types(value, type_names):
        issues.append(
            ParamValidationIssue(
                path,
                f"value {value!r} (type {type(value).__name__}) "
                f"does not match schema types {list(type_names)!r}",
            )
        )
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        if isinstance(props, dict):
            for key, sub_schema in props.items():
                if not isinstance(sub_schema, dict):
                    continue
                sub_path = f"{path}.{key}" if path else key
                if key in value:
                    issues.extend(
                        validate_param_value(value[key], sub_schema, path=sub_path)
                    )
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict) and item_schema:
            for idx, item in enumerate(value):
                sub_path = f"{path}[{idx}]" if path else f"[{idx}]"
                issues.extend(
                    validate_param_value(item, item_schema, path=sub_path)
                )
    return issues


def validate_tool_arguments(
    args: Dict[str, Any],
    func_name: str,
    schema_index: Dict[str, Dict[str, Dict[str, Any]]],
    *,
    required: Optional[Sequence[str]] = None,
) -> List[ParamValidationIssue]:
    func_props = schema_index.get(func_name) or {}
    issues: List[ParamValidationIssue] = []
    if required:
        for key in required:
            if key not in args:
                issues.append(
                    ParamValidationIssue(key, "required parameter is missing")
                )
    for key, value in args.items():
        pschema = func_props.get(key) or {}
        if pschema:
            issues.extend(validate_param_value(value, pschema, path=key))
    return issues


def format_issues_for_llm(
    issues: Sequence[ParamValidationIssue],
    *,
    tool_name: str = "",
) -> str:
    return ToolArgValidationError(list(issues), tool_name=tool_name).to_llm_feedback()


def assert_valid_tool_arguments(
    args: Dict[str, Any],
    func_name: str,
    schema_index: Dict[str, Dict[str, Dict[str, Any]]],
    *,
    required: Optional[Sequence[str]] = None,
) -> None:
    issues = validate_tool_arguments(
        args, func_name, schema_index, required=required
    )
    if issues:
        raise ToolArgValidationError(issues, tool_name=func_name)
