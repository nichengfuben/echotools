from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping

__all__ = ["format_entml_tool_descs"]

# 参数 schema 字段顺序：properties 优先，type 靠后（对齐示范排版）
_SCHEMA_KEY_ORDER = (
    "properties",
    "items",
    "enum",
    "required",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "default",
    "additionalProperties",
    "oneOf",
    "anyOf",
    "allOf",
    "title",
    "description",
    "type",
)

_DESC_LINE_RE = re.compile(
    r'^(\s*)"description": "((?:[^"\\]|\\.)*)"(,?)$',
    re.MULTILINE,
)


def _sort_schema_keys(node: Any) -> Any:
    """递归整理 JSON Schema 字段顺序（properties 的键名保持原序）。"""
    if isinstance(node, list):
        return [_sort_schema_keys(item) for item in node]
    if not isinstance(node, dict):
        return node

    ordered_keys = [key for key in _SCHEMA_KEY_ORDER if key in node]
    remaining_keys = sorted(key for key in node if key not in _SCHEMA_KEY_ORDER)
    out: Dict[str, Any] = {}
    for key in ordered_keys + remaining_keys:
        value = node[key]
        if key == "properties" and isinstance(value, Mapping):
            out[key] = {
                prop_name: _sort_schema_keys(prop_schema)
                for prop_name, prop_schema in value.items()
            }
        else:
            out[key] = _sort_schema_keys(value)
    return out


def _normalize_parameters(params: Any) -> Dict[str, Any]:
    if not isinstance(params, dict):
        return {"type": "object", "properties": {}}
    normalized = dict(params)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    return _sort_schema_keys(normalized)


def _escape_multiline_description_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace('"', '\\"')


def _expand_description_multiline(json_text: str) -> str:
    """将 description 中的 \\n 展开为可读多行（对齐 antml 示范排版）。"""

    def _repl(match: re.Match[str]) -> str:
        indent, escaped, comma = match.groups()
        decoded = json.loads('"' + escaped + '"')
        if "\n" not in decoded:
            return match.group(0)
        lines = decoded.split("\n")
        first = _escape_multiline_description_line(lines[0])
        if len(lines) == 1:
            return f'{indent}"description": "{first}"{comma}'
        body = first + "\n" + "\n".join(
            _escape_multiline_description_line(line) for line in lines[1:]
        )
        return f'{indent}"description": "{body}"{comma}'

    return _DESC_LINE_RE.sub(_repl, json_text)


def _format_parameters_json(params: Mapping[str, Any]) -> str:
    sorted_params = _sort_schema_keys(dict(params))
    body = json.dumps(sorted_params, ensure_ascii=False, indent=2)
    return _expand_description_multiline(body)


def format_entml_tool_descs(tools: List[Dict[str, Any]]) -> str:
    """将工具列表格式化为 ### name + Description + parameters JSON（对齐 entml 示范）。"""
    if not tools:
        return ""

    blocks: List[str] = []
    for tool in tools:
        fn = tool.get("function", tool)
        name = str(fn.get("name") or "unknown")
        description = fn.get("description") or ""
        # Description 外置为 JSON 字符串字面量（含转义），与示范一致
        desc_literal = json.dumps(description, ensure_ascii=False)
        params_body = _format_parameters_json(_normalize_parameters(fn.get("parameters")))
        blocks.append(
            f"### {name}\n\n"
            f"Description: {desc_literal}\n\n"
            f"```json\n{params_body}\n```"
        )
    return "\n\n".join(blocks)
