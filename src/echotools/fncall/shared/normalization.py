"""内容规范化和工具描述格式化。

从 src/core/tools.py 迁移（原 lines 759-843）。
"""

from __future__ import annotations

import json
from typing import Any, List

_LT = chr(60)
_GT = chr(62)
_DQ = chr(34)


def _tag(name, attrs=""):
    """构建 XML 开标签。"""
    if attrs:
        return _LT + name + " " + attrs + _GT
    return _LT + name + _GT


def _ctag(name):
    """构建 XML 闭标签。"""
    return _LT + "/" + name + _GT


def normalize_content(content: Any) -> str:
    """将消息 content 字段规范化为纯字符串。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" or "text" in item:
                    text_val = item.get("text", "")
                    parts.append(str(text_val) if text_val is not None else "")
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return chr(10).join(p for p in parts if p)
    if isinstance(content, dict):
        if "text" in content:
            val = content["text"]
            return str(val) if val is not None else ""
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _render_schema_prop(prop_name, prop_info, required_list, depth, max_depth=4):
    """递归渲染单个 schema 属性为 XML 行列表。"""
    if not isinstance(prop_info, dict):
        return []

    indent = "  " * depth
    pt = prop_info.get("type") or "string"
    req_str = "true" if prop_name in required_list else "false"

    attr_str = 'name=' + _DQ + prop_name + _DQ + ' type=' + _DQ + pt + _DQ + ' required=' + _DQ + req_str + _DQ
    lines = [indent + _tag("parameter", attr_str)]

    pd = prop_info.get("description") or ""
    if pd:
        lines.append(indent + _tag("description") + pd + _ctag("description"))

    enum_vals = prop_info.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        lines.append(indent + _tag("enum") + ", ".join(map(str, enum_vals)) + _ctag("enum"))

    if "default" in prop_info:
        lines.append(indent + _tag("default") + str(prop_info["default"]) + _ctag("default"))

    # Handle oneOf / anyOf / allOf
    for combiner_key in ("oneOf", "anyOf", "allOf"):
        combiner = prop_info.get(combiner_key)
        if isinstance(combiner, list) and combiner:
            variant_descs = []
            for variant in combiner:
                if isinstance(variant, dict):
                    v_type = variant.get("type", "unknown")
                    v_desc = variant.get("description", "")
                    desc_part = " (" + v_desc + ")" if v_desc else ""
                    variant_descs.append(v_type + desc_part)
            if variant_descs:
                lines.append(indent + _tag(combiner_key) + ", ".join(variant_descs) + _ctag(combiner_key))

    # Handle additionalProperties
    addl_props = prop_info.get("additionalProperties")
    if isinstance(addl_props, dict) and addl_props and depth < max_depth:
        addl_type = addl_props.get("type", "any")
        lines.append(indent + _tag("additionalProperties", 'type=' + _DQ + addl_type + _DQ))

    # Recurse into nested object properties
    if pt == "object" and depth < max_depth:
        sub_props = prop_info.get("properties") or {}
        sub_required = prop_info.get("required") or []
        if sub_props:
            lines.append(indent + _tag("properties"))
            for sub_name, sub_info in sub_props.items():
                lines.extend(_render_schema_prop(sub_name, sub_info, sub_required, depth + 1, max_depth))
            lines.append(indent + _ctag("properties"))

    # Recurse into array items
    if pt == "array" and depth < max_depth:
        items_schema = prop_info.get("items")
        if isinstance(items_schema, dict) and items_schema:
            items_type = items_schema.get("type", "any")
            lines.append(indent + _tag("items", 'type=' + _DQ + items_type + _DQ))
            if items_type == "object":
                item_props = items_schema.get("properties") or {}
                item_required = items_schema.get("required") or []
                if item_props:
                    for item_name, item_info in item_props.items():
                        lines.extend(_render_schema_prop(item_name, item_info, item_required, depth + 1, max_depth))
            else:
                item_desc = items_schema.get("description", "")
                if item_desc:
                    lines.append(indent + "  " + _tag("description") + item_desc + _ctag("description"))
                item_enum = items_schema.get("enum")
                if isinstance(item_enum, list) and item_enum:
                    lines.append(indent + "  " + _tag("enum") + ", ".join(map(str, item_enum)) + _ctag("enum"))
            lines.append(indent + _ctag("items"))

    lines.append(indent + _ctag("parameter"))
    return lines


def format_tool_descs(tools):
    """将 OpenAI 格式工具定义列表格式化为 XML 描述字符串。"""
    if not tools:
        return ""

    parts = []
    for tool in tools:
        fn = tool.get("function", tool)
        name = fn.get("name") or "unknown"
        desc = fn.get("description") or ""
        params = fn.get("parameters") or {}
        props = params.get("properties") or {}
        required = params.get("required") or []

        lines = [_tag("tool", 'name=' + _DQ + name + _DQ)]
        if desc:
            lines.append(_tag("description") + desc + _ctag("description"))
        lines.append(_tag("parameters"))

        for pn, pi in props.items():
            if not isinstance(pi, dict):
                continue
            lines.extend(_render_schema_prop(pn, pi, required, depth=0, max_depth=4))

        lines.append(_ctag("parameters"))

        examples = fn.get("input_examples")
        if isinstance(examples, list) and examples:
            lines.append(_tag("input_examples"))
            for ex in examples:
                lines.append(_tag("example") + json.dumps(ex, ensure_ascii=False) + _ctag("example"))
            lines.append(_ctag("input_examples"))

        lines.append(_ctag("tool"))
        parts.append(chr(10).join(lines))

    return (chr(10) + chr(10)).join(parts)
