from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .entml_patterns import (
    BLOCK_RE,
    INVOKE_RE,
    PARAM_RE,
    PARAMETERS_RE,
    extract_parameter_type_attr,
    parse_sub_tags,
)
from .entml_values import coerce_entml_arguments, coerce_entml_parameter_value


def parse_invoke_args(
    body: str,
    name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Dict[str, Any]:
    func_props = (schema_index or {}).get(name) or {}

    params_m = PARAMETERS_RE.search(body)
    if params_m:
        params_content = params_m.group(1).strip()
        try:
            parsed = json.loads(params_content)
            if isinstance(parsed, dict):
                return coerce_entml_arguments(parsed, name, schema_index)
            return {"value": parsed}
        except json.JSONDecodeError:
            sub_args = parse_sub_tags(params_content, schema_index, name)
            if sub_args:
                return coerce_entml_arguments(sub_args, name, schema_index)
            return {"value": params_content}

    args: Dict[str, Any] = {}
    for param_m in PARAM_RE.finditer(body):
        pname = param_m.group(1).strip()
        attrs = param_m.group(2) or ""
        pval = param_m.group(3)
        type_hint = extract_parameter_type_attr(attrs)
        pschema = func_props.get(pname) or {}
        args[pname] = coerce_entml_parameter_value(
            pval,
            pschema or None,
            type_hint=type_hint if not pschema else None,
        )

    return coerce_entml_arguments(args, name, schema_index)


def parse_entml_tool_calls(
    text: str,
    tools: Optional[List[Dict[str, Any]]],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    tool_calls: List[Dict[str, Any]] = []
    for block_m in BLOCK_RE.finditer(text):
        block_body = block_m.group(1)
        for invoke_m in INVOKE_RE.finditer(block_body):
            name = invoke_m.group(1).strip()
            args = parse_invoke_args(invoke_m.group(2), name, schema_index)
            arguments = json.dumps(args, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": f"call_{len(tool_calls):04d}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
    return tool_calls


def format_entml_parameter_value(value: Any) -> str:
    """标量原样输出；列表/对象序列化为 JSON。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def format_entml_tool_calls(tool_calls: List[Dict[str, Any]]) -> str:
    """将 tool_call 列表渲染为 entml function_calls 块。"""
    if not tool_calls:
        return ""

    invokes: List[str] = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = str(fn.get("name") or "")
        args_raw = fn.get("arguments") or "{}"
        try:
            args_obj = json.loads(args_raw)
            if not isinstance(args_obj, dict):
                args_obj = {"value": args_obj}
        except (TypeError, json.JSONDecodeError):
            args_obj = {"value": args_raw}

        param_lines: List[str] = []
        for key, value in args_obj.items():
            rendered = format_entml_parameter_value(value)
            param_lines.append(
                f'<entml:parameter name="{key}">{rendered}</entml:parameter>'
            )
        body = "\n".join(param_lines)
        invokes.append(f'<entml:invoke name="{name}">\n{body}\n</entml:invoke>')

    inner = "\n".join(invokes)
    return f"<entml:function_calls>\n{inner}\n</entml:function_calls>"
