"""从 ``<tool>`` 块解析模型误输出的 history 风格工具调用。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .entml_patterns import INVOKE_RE, normalize_entml_name
from .entml_values import coerce_entml_arguments

_TOOL_BLOCK_RE = re.compile(
    r"<tool\s*>\s*([\s\S]*?)\s*</tool\s*>",
    re.IGNORECASE,
)
_INNER_TOOL_TAG_RE = re.compile(
    r"<([A-Za-z][A-Za-z0-9_]*)\s*>\s*([\s\S]*?)(?:</\1\s*>|(?=</tool\s*>)|$)",
    re.IGNORECASE,
)
_BRACE_TOOL_HEAD_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\s*:\s*")
# 工具结果常见行号泄漏（Read 伪块）
_OUTPUT_LINE_RE = re.compile(r"^\s*\d+\s+\S", re.MULTILINE)


def _known_tool_names(
    tools: Optional[List[Dict[str, Any]]],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Set[str]:
    if schema_index:
        return set(schema_index.keys())
    names: Set[str] = set()
    for tool in tools or []:
        fn = tool.get("function") or {}
        name = fn.get("name")
        if name:
            names.add(normalize_entml_name(str(name)))
    return names


def _decode_brace_value(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _args_from_parsed(name: str, parsed: Any) -> Dict[str, Any]:
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def _extract_first_brace_tool_call(body: str) -> Optional[Tuple[str, Any]]:
    """从正文提取首个 ``{Tool: json}``（允许后面跟工具输出 tail）。"""
    match = _BRACE_TOOL_HEAD_RE.search(body)
    if not match:
        return None
    name = normalize_entml_name(match.group(1))
    rest = body[match.end() :].lstrip()
    if not rest or rest[0] not in "{[":
        return None
    try:
        parsed, end = json.JSONDecoder().raw_decode(rest)
    except json.JSONDecodeError:
        return None
    after = rest[end:].lstrip()
    if after.startswith("}"):
        after = after[1:].lstrip()
    if after and _OUTPUT_LINE_RE.search(after):
        return None
    return name, parsed


def _parse_inner_tag_calls(
    body: str,
    known: Set[str],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> List[Tuple[str, Dict[str, Any]]]:
    calls: List[Tuple[str, Dict[str, Any]]] = []
    for match in _INNER_TOOL_TAG_RE.finditer(body):
        name = normalize_entml_name(match.group(1))
        if known and name not in known:
            continue
        raw = (match.group(2) or "").strip()
        if not raw:
            continue
        parsed = _decode_brace_value(raw)
        if isinstance(parsed, str) and not raw.startswith(("{", "[")):
            continue
        args = _args_from_parsed(name, parsed)
        args = coerce_entml_arguments(args, name, schema_index)
        calls.append((name, args))
    return calls


def _parse_brace_calls(
    body: str,
    known: Set[str],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """多块 ``{Tool: ...}`` 视为 history 回放，不解析（避免 Edit 伪块误触）。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    brace_lines = [
        ln for ln in lines if ln.startswith("{") and _BRACE_TOOL_HEAD_RE.match(ln)
    ]
    if len(brace_lines) > 1:
        return []
    parsed = _extract_first_brace_tool_call(body)
    if not parsed:
        return []
    name, value = parsed
    if known and name not in known:
        return []
    args = coerce_entml_arguments(_args_from_parsed(name, value), name, schema_index)
    return [(name, args)]


def parse_tool_block_body(
    body: str,
    *,
    tools: Optional[List[Dict[str, Any]]] = None,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    allow_brace_format: bool = True,
) -> List[Tuple[str, Dict[str, Any]]]:
    """从 ``<tool>`` 块正文提取 ``[(name, args), ...]``（解析不出则 ``[]``）。"""
    text = (body or "").strip()
    if not text:
        return []
    known = _known_tool_names(tools, schema_index)

    inner = _parse_inner_tag_calls(text, known, schema_index)
    if inner:
        return inner

    if not allow_brace_format:
        return []

    return _parse_brace_calls(text, known, schema_index)


def parse_tool_block_calls(
    text: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """扫描 ``<tool>...</tool>`` 块并解析为 OpenAI tool_calls 列表。"""
    if not text or "<tool" not in text.lower():
        return []

    allow_brace = not bool(INVOKE_RE.search(text))
    tool_calls: List[Dict[str, Any]] = []
    for match in _TOOL_BLOCK_RE.finditer(text):
        for name, args in parse_tool_block_body(
            match.group(1),
            tools=tools,
            schema_index=schema_index,
            allow_brace_format=allow_brace,
        ):
            tool_calls.append(
                {
                    "id": f"call_{len(tool_calls):04d}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
    return tool_calls
