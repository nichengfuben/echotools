from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from echotools.exec.fncall.shared.coercion import (
    _coerce_param_value,
    _resolve_effective_type,
)

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

# --- mangled param tail ---
#
# 模型偶发把 schema 尾缀 ``", "description": "...", "timeout": N}}`` 粘进标量 parameter。
# 通用规则：仅当「从候选起点到 EOS」整段都是该尾缀（可未写完）时才截断；
# 一旦后续偏离（例如内嵌 JSON 的 ``"method"``），一律视为正文。不依赖参数名黑名单。

_MANGLED_PARAM_JSON_TAIL_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"timeout"\s*:\s*(\d+)\s*\}\}?\s*$',
    re.DOTALL,
)

_DESC_KEY = "description"
_TIMEOUT_KEY = "timeout"


def _param_value_is_json_container(value: str) -> bool:
    stripped = (value or "").lstrip()
    return bool(stripped) and stripped[0] in "{["


def _match_schema_key_prefix(
    text: str,
    pos: int,
    *,
    allowed: Tuple[str, ...] = (_DESC_KEY, _TIMEOUT_KEY),
) -> Optional[Tuple[str, int]]:
    """匹配 schema 键。

    返回 ``("<key>"|"partial", new_pos)``；已偏离则 ``None``。
    """
    if pos >= len(text):
        return ("partial", pos)
    for key in allowed:
        if text.startswith(key, pos):
            return (key, pos + len(key))
    remain = text[pos:]
    for key in allowed:
        if key.startswith(remain):
            return ("partial", len(text))
    return None


def _consume_json_string_body(text: str, pos: int) -> Tuple[int, bool]:
    """从 JSON 字符串内容起点消费（不含开引号）。返回 ``(new_pos, closed)``。"""
    i = pos
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text):
                return len(text), False
            i += 2
            continue
        if ch == '"':
            return i + 1, True
        i += 1
    return len(text), False


def _is_mangled_schema_tail_suffix(suffix: str) -> bool:
    """``suffix`` 是否整段为 mangled schema 尾缀（允许流式未写完）。

    必须以 ``description``（或其真前缀）起头；禁止把文末单独的
    ``", "timeout": N`` 当成尾缀（避免截断正文 JSON）。
    """
    if not suffix:
        return False
    m = re.match(r'^"\s*,\s*"', suffix)
    if not m:
        return False
    pos = m.end()
    # 首键只能是 description（或其真前缀），避免 ", \"t" 误伤 type/timeout 正文
    key_match = _match_schema_key_prefix(suffix, pos, allowed=(_DESC_KEY,))
    if key_match is None:
        return False
    key, pos = key_match
    if key == "partial":
        return pos == len(suffix)
    if key != _DESC_KEY:
        return False
    if pos >= len(suffix):
        return True
    if suffix[pos] != '"':
        return False
    pos += 1
    m_colon = re.match(r"\s*:\s*", suffix[pos:])
    if not m_colon:
        return bool(re.match(r"\s*$", suffix[pos:]))
    pos += m_colon.end()
    if pos >= len(suffix):
        return True
    if suffix[pos] != '"':
        return False
    pos += 1
    pos, closed = _consume_json_string_body(suffix, pos)
    if not closed:
        return pos == len(suffix)
    if pos == len(suffix):
        # description 已闭合、timeout 尚未出现：流式未完成或残缺尾缀，仍视为 mangled
        return True
    m_rest = re.match(r"\s*,\s*", suffix[pos:])
    if not m_rest:
        return re.match(r"\s*\}{0,2}\s*$", suffix[pos:]) is not None
    pos += m_rest.end()
    if pos >= len(suffix):
        return True
    if suffix[pos] != '"':
        return False
    pos += 1
    key2 = _match_schema_key_prefix(suffix, pos, allowed=(_TIMEOUT_KEY,))
    if key2 is None:
        return False
    key2_name, pos = key2
    if key2_name == "partial":
        return pos == len(suffix)
    if key2_name != _TIMEOUT_KEY:
        return False
    if pos >= len(suffix):
        return True
    if suffix[pos] != '"':
        return False
    pos += 1
    m_colon2 = re.match(r"\s*:\s*", suffix[pos:])
    if not m_colon2:
        return bool(re.match(r"\s*$", suffix[pos:]))
    pos += m_colon2.end()
    m_num2 = re.match(r"\d*", suffix[pos:])
    assert m_num2 is not None
    pos += m_num2.end()
    return re.match(r"\s*\}{0,2}\s*$", suffix[pos:]) is not None


def _ambiguous_comma_hold_end(value: str) -> int:
    """值以 ``",`` / ``", "`` 结尾且下一键未明时，返回应保留到的终点（含引号）。

    流式在键名出现前无法区分 mangled 尾缀与正文 JSON 换键；先截到引号以保持
    partial_json 单调，待后续字符证明不是 description 后再放出全文。
    """
    m = re.search(r'"\s*,\s*"?$', value)
    if not m:
        return -1
    return m.start() + 1


def _find_mangled_schema_tail_start(value: str) -> int:
    """返回 mangled 尾缀起点；无则 -1。

    取最左合法起点，保证一旦出现 ``", "description"...`` 就截在 command 侧，
    避免流式先发出更长前缀再无法回缩。
    """
    starts = [m.start() for m in re.finditer(r'"\s*,\s*"', value)]
    for start in starts:
        if _is_mangled_schema_tail_suffix(value[start:]):
            return start
    hold = _ambiguous_comma_hold_end(value)
    if hold >= 0:
        # 把 hold 点前的引号视为尾缀起点（与合法 mangled 起点同形）
        return hold - 1
    return -1


def mangled_json_param_tail_in_progress(value: str) -> bool:
    """值末尾正在形成 mangled schema 尾缀（尚未收齐）时抑制 partial_json 增长。"""
    if not value or _param_value_is_json_container(value):
        return False
    start = _find_mangled_schema_tail_start(value)
    if start < 0:
        return False
    if _MANGLED_PARAM_JSON_TAIL_RE.search(value[start:]):
        return False
    return True


def split_mangled_json_param_tail(
    value: str,
    *,
    param_name: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """模型把 ``", "description": ..., "timeout": ...}}`` 误写入 parameter 值时的拆分。"""
    _ = param_name
    if not value:
        return value, {}
    if _param_value_is_json_container(value):
        try:
            json.loads(value)
            return value, {}
        except json.JSONDecodeError:
            return value, {}

    match = _MANGLED_PARAM_JSON_TAIL_RE.search(value)
    if match:
        return value[: match.start() + 1], {
            "description": match.group(1),
            "timeout": int(match.group(2)),
        }

    start = _find_mangled_schema_tail_start(value)
    if start < 0:
        return value, {}
    return value[: start + 1], {}



