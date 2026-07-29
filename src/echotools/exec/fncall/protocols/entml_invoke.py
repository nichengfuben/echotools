from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .entml_patterns import (
    BARE_INVOKE_CHILD_RE,
    INVOKE_DIRECT_CHILD_OPEN_RE,
    INVOKE_DIRECT_CHILD_RE,
    INVOKE_DIRECT_CHILD_SKIP,
    INVOKE_RE,
    PARAM_RE,
    PARAMETERS_RE,
    extract_attr_value,
    extract_parameter_type_attr,
    normalize_entml_name,
    parse_sub_tags,
    split_mangled_json_param_tail,
    synthetic_close_invoke_body,
)
from .entml_values import coerce_entml_arguments, coerce_entml_parameter_value


def _parse_direct_child_tags(
    body: str,
    args: Dict[str, Any],
    func_props: Dict[str, Dict[str, Any]],
) -> None:
    """模型用 ``<key>value</key>`` 代替 ``<parameter name=\"key\">``。"""
    for match in INVOKE_DIRECT_CHILD_RE.finditer(body):
        key = normalize_entml_name(match.group(1))
        if not key or key.lower() in INVOKE_DIRECT_CHILD_SKIP or key in args:
            continue
        raw = (match.group(2) or "").strip()
        args[key] = coerce_entml_parameter_value(
            raw,
            func_props.get(key) or None,
        )


def _parse_bare_invoke_children(
    body: str,
    args: Dict[str, Any],
    func_props: Dict[str, Dict[str, Any]],
) -> None:
    for match in BARE_INVOKE_CHILD_RE.finditer(body):
        key = normalize_entml_name(match.group(1))
        if not key or key in args:
            continue
        raw = (match.group(2) or "").strip()
        args[key] = coerce_entml_parameter_value(
            raw,
            func_props.get(key) or None,
        )


def parse_invoke_args(
    body: str,
    name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Dict[str, Any]:
    func_props = (schema_index or {}).get(name) or {}
    if "</entml:invoke>" in body:
        body = body[: body.index("</entml:invoke>")]
    body = synthetic_close_invoke_body(body)

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
        attrs = param_m.group(1) or ""
        pname = extract_attr_value(attrs, "name")
        if not pname:
            continue
        pname = normalize_entml_name(pname)
        pval = (param_m.group(2) or "").strip()
        pval, extra = split_mangled_json_param_tail(pval)
        type_hint = extract_parameter_type_attr(attrs)
        pschema = func_props.get(pname) or {}
        args[pname] = coerce_entml_parameter_value(
            pval,
            pschema or None,
            type_hint=type_hint,
        )
        for extra_key, extra_val in extra.items():
            if extra_key in args:
                continue
            extra_schema = func_props.get(extra_key) or {}
            if isinstance(extra_val, (int, float, bool)):
                args[extra_key] = extra_val
            else:
                args[extra_key] = coerce_entml_parameter_value(
                    str(extra_val),
                    extra_schema or None,
                )

    _parse_bare_invoke_children(body, args, func_props)
    _parse_direct_child_tags(body, args, func_props)

    return args


def parse_entml_tool_calls(
    text: str,
    tools: Optional[List[Dict[str, Any]]],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> List[Dict[str, Any]]:
    tool_calls: List[Dict[str, Any]] = []
    for invoke_m in INVOKE_RE.finditer(text):
        attrs = invoke_m.group(1) or ""
        name = extract_attr_value(attrs, "name")
        if not name:
            continue
        name = normalize_entml_name(name)
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
    """将 tool_call 列表渲染为裸 ``<entml:invoke>`` 块（无 function_calls 外壳）。"""
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

    return "\n".join(invokes)
