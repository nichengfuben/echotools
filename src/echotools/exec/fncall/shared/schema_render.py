from __future__ import annotations

from typing import Any, Dict, List

_LT = chr(60)
_GT = chr(62)
_DQ = chr(34)


def _tag(name: str, attrs: str = "") -> str:
    if attrs:
        return _LT + name + " " + attrs + _GT
    return _LT + name + _GT


def _ctag(name: str) -> str:
    return _LT + "/" + name + _GT


def _render_combiner_lines(prop_info: Dict[str, Any], indent: str) -> List[str]:
    lines: List[str] = []
    for combiner_key in ("oneOf", "anyOf", "allOf"):
        combiner = prop_info.get(combiner_key)
        if not isinstance(combiner, list) or not combiner:
            continue
        variant_descs = []
        for variant in combiner:
            if not isinstance(variant, dict):
                continue
            v_type = variant.get("type", "unknown")
            v_desc = variant.get("description", "")
            desc_part = " (" + v_desc + ")" if v_desc else ""
            variant_descs.append(v_type + desc_part)
        if variant_descs:
            lines.append(
                indent + _tag(combiner_key) + ", ".join(variant_descs) + _ctag(combiner_key)
            )
    return lines


def _render_object_children(
    prop_info: Dict[str, Any], depth: int, max_depth: int
) -> List[str]:
    if depth >= max_depth:
        return []
    sub_props = prop_info.get("properties") or {}
    if not sub_props:
        return []
    indent = "  " * depth
    sub_required = prop_info.get("required") or []
    lines = [indent + _tag("properties")]
    for sub_name, sub_info in sub_props.items():
        lines.extend(_render_schema_prop(sub_name, sub_info, sub_required, depth + 1, max_depth))
    lines.append(indent + _ctag("properties"))
    return lines


def _render_array_items(
    items_schema: Dict[str, Any], depth: int, max_depth: int
) -> List[str]:
    indent = "  " * depth
    items_type = items_schema.get("type", "any")
    lines = [indent + _tag("items", 'type=' + _DQ + items_type + _DQ)]
    if items_type == "object" and depth < max_depth:
        item_props = items_schema.get("properties") or {}
        item_required = items_schema.get("required") or []
        for item_name, item_info in item_props.items():
            lines.extend(
                _render_schema_prop(item_name, item_info, item_required, depth + 1, max_depth)
            )
    else:
        item_desc = items_schema.get("description", "")
        if item_desc:
            lines.append(indent + "  " + _tag("description") + item_desc + _ctag("description"))
        item_enum = items_schema.get("enum")
        if isinstance(item_enum, list) and item_enum:
            lines.append(
                indent + "  " + _tag("enum") + ", ".join(map(str, item_enum)) + _ctag("enum")
            )
    lines.append(indent + _ctag("items"))
    return lines


def _render_schema_prop(
    prop_name: str, prop_info: Any, required_list: List[str], depth: int, max_depth: int = 4
) -> List[str]:
    if not isinstance(prop_info, dict):
        return []

    indent = "  " * depth
    pt = prop_info.get("type") or "string"
    req_str = "true" if prop_name in required_list else "false"
    attr_str = (
        "name=" + _DQ + prop_name + _DQ + " type=" + _DQ + pt + _DQ
        + " required=" + _DQ + req_str + _DQ
    )
    lines = [indent + _tag("parameter", attr_str)]

    pd = prop_info.get("description") or ""
    if pd:
        lines.append(indent + _tag("description") + pd + _ctag("description"))

    enum_vals = prop_info.get("enum")
    if isinstance(enum_vals, list) and enum_vals:
        lines.append(indent + _tag("enum") + ", ".join(map(str, enum_vals)) + _ctag("enum"))

    if "default" in prop_info:
        lines.append(indent + _tag("default") + str(prop_info["default"]) + _ctag("default"))

    lines.extend(_render_combiner_lines(prop_info, indent))

    addl_props = prop_info.get("additionalProperties")
    if isinstance(addl_props, dict) and addl_props and depth < max_depth:
        addl_type = addl_props.get("type", "any")
        lines.append(indent + _tag("additionalProperties", 'type=' + _DQ + addl_type + _DQ))

    if pt == "object":
        lines.extend(_render_object_children(prop_info, depth, max_depth))

    if pt == "array" and depth < max_depth:
        items_schema = prop_info.get("items")
        if isinstance(items_schema, dict) and items_schema:
            lines.extend(_render_array_items(items_schema, depth, max_depth))

    lines.append(indent + _ctag("parameter"))
    return lines
