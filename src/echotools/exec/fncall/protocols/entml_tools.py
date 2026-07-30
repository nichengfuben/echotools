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


def _humanize_schema_descriptions(node: Any) -> Any:
    """递归还原 schema 中 description 的字面量转义（\\n、\\_ 等）。"""
    if isinstance(node, list):
        return [_humanize_schema_descriptions(item) for item in node]
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "description" and isinstance(value, str):
                out[key] = _normalize_tool_description(value)
            else:
                out[key] = _humanize_schema_descriptions(value)
        return out
    return node


def _format_description_literal(text: str) -> str:
    """prompt 内 parameters JSON 的 description：真换行、不转义引号与常见字符。"""
    if not text:
        return '""'
    return f'"{text}"'


def _expand_description_multiline(json_text: str) -> str:
    """将 description 字段从 JSON 转义形式改为可读文本（仅处理 description 键）。"""

    def _repl(match: re.Match[str]) -> str:
        indent, escaped, comma = match.groups()
        try:
            decoded = json.loads('"' + escaped + '"')
        except json.JSONDecodeError:
            return match.group(0)
        if not isinstance(decoded, str):
            return match.group(0)
        decoded = _normalize_tool_description(decoded)
        return f'{indent}"description": {_format_description_literal(decoded)}{comma}'

    return _DESC_LINE_RE.sub(_repl, json_text)


def _normalize_tool_description(description: Any) -> str:
    """将上游字面量 \\n / \\_ / \\* 等还原为可读文本。"""
    if not description:
        return ""
    text = str(description)
    while "\\n" in text or "\\r" in text or "\\t" in text:
        prev = text
        text = (
            text.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )
        if text == prev:
            break
    for old, new in (("\\_", "_"), ("\\*", "*")):
        text = text.replace(old, new)
    return text


def _format_top_level_description(description: Any) -> str:
    """顶层 Description：真换行排版，不再包 JSON 字符串引号。"""
    text = _normalize_tool_description(description)
    if not text:
        return "Description:"
    return f"Description:\n{text}"


def _format_parameters_json(params: Mapping[str, Any]) -> str:
    normalized = _humanize_schema_descriptions(dict(params))
    sorted_params = _sort_schema_keys(normalized)
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
        desc_block = _format_top_level_description(description)
        params_body = _format_parameters_json(_normalize_parameters(fn.get("parameters")))
        blocks.append(
            f"### {name}\n\n"
            f"{desc_block}\n\n"
            f"```json\n{params_body}\n```"
        )
    return "\n\n".join(blocks)
