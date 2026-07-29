from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from echotools.exec.fncall.shared.coercion import _coerce_param_value, _resolve_effective_type

_TYPE_HINT_TO_JSON_TYPE = {
    "str": "string",
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "double": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "array": "array",
    "list": "array",
    "object": "object",
    "dict": "object",
}


def _schema_from_type_hint(type_hint: str) -> Optional[Dict[str, Any]]:
    json_type = _TYPE_HINT_TO_JSON_TYPE.get((type_hint or "").strip().lower())
    if not json_type:
        return None
    schema: Dict[str, Any] = {"type": json_type}
    if json_type == "array":
        schema["items"] = {}
    return schema


def resolve_entml_parameter_schema(
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """解析参数 effective schema：模型 ``type`` 属性优先，否则用工具 schema。"""
    hint_schema = _schema_from_type_hint(type_hint) if type_hint else None
    if hint_schema:
        return hint_schema
    if schema:
        return schema
    return None


def coerce_entml_parameter_value(
    raw: str,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Any:
    """将 entml 参数文本转为 Python 值。

    类型优先级：parameter 上的 ``type`` 属性 > 工具 JSON Schema > 默认 string。
    """
    effective = resolve_entml_parameter_schema(schema, type_hint)
    if effective:
        return _coerce_param_value(raw, effective)

    stripped = (raw or "").strip()
    if not stripped:
        return ""

    if stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped

    return stripped


def effective_entml_param_json_type(
    value: str,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> str:
    """流式 partial_json 与 batch 共用：模型 type 优先，否则 schema，再否则按值推断。"""
    effective = resolve_entml_parameter_schema(schema, type_hint)
    if effective:
        resolved = _resolve_effective_type(effective)
        if resolved:
            return resolved
    stripped = (value or "").lstrip()
    if stripped.startswith("["):
        return "array"
    if stripped.startswith("{"):
        return "object"
    return "string"


def _coerce_entml_arg_value(
    value: Any,
    schema: Optional[Dict[str, Any]] = None,
    type_hint: Optional[str] = None,
) -> Any:
    """将已解析的 Python 值再按 type_hint / schema 归一（与 batch 单参路径一致）。"""
    if isinstance(value, str):
        return coerce_entml_parameter_value(value, schema, type_hint=type_hint)
    if isinstance(value, (dict, list)):
        return coerce_entml_parameter_value(
            json.dumps(value, ensure_ascii=False),
            schema,
            type_hint=type_hint,
        )
    if value is None:
        return coerce_entml_parameter_value("", schema, type_hint=type_hint)
    return coerce_entml_parameter_value(str(value), schema, type_hint=type_hint)


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
        if pschema:
            out[key] = _coerce_entml_arg_value(value, pschema)
        else:
            out[key] = value
    return out


# --- tool description formatting (from entml_tools) ---


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

# --- mangled param tail (from entml_patterns) ---

_MANGLED_PARAM_JSON_TAIL_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"timeout"\s*:\s*(\d+)\s*\}\}?\s*$',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_START_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_EARLY_RE = re.compile(
    r'"\s*,\s*"(?:description|timeout)\b',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE = re.compile(
    r'"\s*,\s*"(?:d|t)',
    re.DOTALL,
)
_MANGLED_TAIL_SKIP_PARAM_NAMES = frozenset(
    {
        "content",
        "contents",
        "text",
        "body",
        "file_path",
        "path",
        "message",
        "html",
        "data",
        "code",
    }
)


_MANGLED_PARAM_JSON_COMMA_QUOTE_END_RE = re.compile(
    r'"\s*,\s*"$',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_COMMA_AFTER_QUOTE_RE = re.compile(
    r'"\s*,\s*$',
    re.DOTALL,
)


def _param_value_is_json_container(value: str) -> bool:
    stripped = (value or "").lstrip()
    return bool(stripped) and stripped[0] in "{["


def mangled_json_param_tail_in_progress(value: str) -> bool:
    """parameter 值中出现误写入 JSON 尾缀但尚未收齐时不应继续增长 partial_json。"""
    if not value or _param_value_is_json_container(value):
        return False
    return bool(_MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE.search(value))


def split_mangled_json_param_tail(
    value: str,
    *,
    param_name: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """模型把 ``", "description": ..., "timeout": ...}}`` 误写入 parameter 值时的拆分。"""
    if not value:
        return value, {}
    if param_name in _MANGLED_TAIL_SKIP_PARAM_NAMES:
        return value, {}
    if _param_value_is_json_container(value):
        try:
            json.loads(value)
            return value, {}
        except json.JSONDecodeError:
            # 合法 JSON 数组/对象（含 options.description 等）不得走标量 command 尾缀启发式。
            return value, {}
    match = _MANGLED_PARAM_JSON_TAIL_RE.search(value)
    if match:
        command = value[: match.start() + 1]
        extra: Dict[str, Any] = {
            "description": match.group(1),
            "timeout": int(match.group(2)),
        }
        return command, extra
    partial = _MANGLED_PARAM_JSON_TAIL_START_RE.search(value)
    if partial:
        return value[: partial.start() + 1], {}
    early = _MANGLED_PARAM_JSON_TAIL_EARLY_RE.search(value)
    if early:
        return value[: early.start() + 1], {}
    inprog = _MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE.search(value)
    if inprog:
        before = value[: inprog.start()]
        matches = list(re.finditer(r'"\s*,\s*"', before))
        if matches:
            return value[: matches[-1].start() + 1], {}
        return value[: inprog.start() + 1], {}
    comma_quote_end = _MANGLED_PARAM_JSON_COMMA_QUOTE_END_RE.search(value)
    if comma_quote_end:
        return value[: comma_quote_end.start() + 1], {}
    comma_after_quote = _MANGLED_PARAM_JSON_COMMA_AFTER_QUOTE_RE.search(value)
    if comma_after_quote:
        return value[: comma_after_quote.start() + 1], {}
    return value, {}



