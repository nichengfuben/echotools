from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping

__all__ = ["format_entml_tool_descs"]

_SCHEMA_KEY_ORDER = (
    "description",
    "type",
    "enum",
    "items",
    "properties",
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


def _format_tool_json(payload: Mapping[str, Any]) -> str:
    sorted_payload = _sort_schema_keys(dict(payload))
    body = json.dumps(sorted_payload, ensure_ascii=False, indent=2)
    return _expand_description_multiline(body)


def format_entml_tool_descs(tools: List[Dict[str, Any]]) -> str:
    """将工具列表格式化为 **name** + JSON Schema 代码块（对齐 entml/antml 示范）。"""
    if not tools:
        return ""

    blocks: List[str] = []
    for tool in tools:
        fn = tool.get("function", tool)
        name = str(fn.get("name") or "unknown")
        payload = {
            "description": fn.get("description") or "",
            "name": name,
            "parameters": _normalize_parameters(fn.get("parameters")),
        }
        body = _format_tool_json(payload)
        blocks.append(f"**{name}**\n\n```json\n{body}\n```")
    return "\n\n".join(blocks)
