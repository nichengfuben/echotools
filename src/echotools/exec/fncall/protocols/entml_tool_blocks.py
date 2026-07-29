"""从 ``<tool>`` 块解析模型误输出的 history 风格工具调用。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .entml_patterns import INVOKE_RE, normalize_entml_name
from .entml_values import coerce_entml_arguments

_TOOL_BLOCK_OPEN_RE = re.compile(r"<tool\s*>", re.IGNORECASE)
_TOOL_BLOCK_CLOSE_RE = re.compile(
    r"(?:</tool\s*>|</system\b[^>]*>|</assistant\s*>)",
    re.IGNORECASE,
)
# legacy 整段匹配（测试/简单场景）
_TOOL_BLOCK_RE = re.compile(
    r"<tool\s*>\s*([\s\S]*?)\s*</tool\s*>",
    re.IGNORECASE,
)
_INNER_TOOL_TAG_RE = re.compile(
    r"<([A-Za-z][A-Za-z0-9_]*)\s*>\s*([\s\S]*?)(?:</\1\s*>|(?=</tool\s*>)|$)",
    re.IGNORECASE,
)
_BRACE_TOOL_HEAD_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\s*:\s*")
# ``{Bash>`` / ``{Read}`` 后接 ``<entml:parameter>`` 的混合格式（``{Edit: json}`` 仍走 history brace）
_MANGLED_BRACE_ENTML_HEAD_RE = re.compile(
    r"^\s*\{([A-Za-z][A-Za-z0-9_]*)\s*(?:>|\})\s*",
    re.MULTILINE,
)
_PARAM_MARKER_RE = re.compile(
    r"<\s*(?:entml:)?parameter\b",
    re.IGNORECASE,
)
# 工具结果常见行号泄漏（Read 伪块）— 仅用于多块 brace 判定
_OUTPUT_LINE_RE = re.compile(r"^\s*\d+\s+\S", re.MULTILINE)
_SCALAR_ARG_KEYS = ("path", "command", "pattern", "query", "file_path")


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


def _args_from_scalar(
    name: str,
    scalar: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Dict[str, Any]:
    """``{Read: path/to/file}`` / ``{Bash: echo hi}`` 等标量行。"""
    func_props = (schema_index or {}).get(name) or {}
    if len(func_props) == 1:
        key = next(iter(func_props))
        return {key: scalar}
    for key in _SCALAR_ARG_KEYS:
        if key in func_props:
            return {key: scalar}
    return {"value": scalar}


def _looks_like_file_path(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if "/" in text or "\\" in text:
        return True
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return True
    return False


def _extract_first_brace_tool_call(body: str) -> Optional[Tuple[str, Any]]:
    """从正文提取首个 ``{Tool: json|scalar}``（允许后面跟工具输出 tail）。"""
    match = _BRACE_TOOL_HEAD_RE.search(body)
    if not match:
        return None
    name = normalize_entml_name(match.group(1))
    rest = body[match.end() :].lstrip()
    if not rest:
        return None
    if rest[0] in "{[":
        try:
            parsed, end = json.JSONDecoder().raw_decode(rest)
        except json.JSONDecodeError:
            return None
        after = rest[end:].lstrip()
        if after.startswith("}"):
            after = after[1:].lstrip()
        # JSON + 行号 tail 为 history Read 伪块；标量 path + tail 仍解析（模型误格式真调用）
        if after and _OUTPUT_LINE_RE.search(after):
            return None
        return name, parsed
    close = rest.find("}")
    if close < 0:
        return None
    scalar = rest[:close].strip()
    if not scalar:
        return None
    after = rest[close + 1 :]
    has_output_tail = bool(_OUTPUT_LINE_RE.search(after))
    # 标量行：仅 path 型 Read/Glob 或带 Read 行号 tail；``{Bash: echo hi}`` 视为 history
    if not has_output_tail and not _looks_like_file_path(scalar):
        return None
    return name, scalar


def _iter_tool_block_spans(text: str) -> Iterator[Tuple[int, int, str]]:
    """yield ``(open_start, close_end, body)``。"""
    if not text or "<tool" not in text.lower():
        return
    pos = 0
    while True:
        open_m = _TOOL_BLOCK_OPEN_RE.search(text, pos)
        if not open_m:
            break
        body_start = open_m.end()
        close_m = _TOOL_BLOCK_CLOSE_RE.search(text, body_start)
        if close_m:
            close_end = close_m.end()
            close_tag = text[close_m.start() : close_m.end()].lower()
            if close_tag.startswith("</system"):
                after = text[close_end:]
                footer = re.match(
                    r"[^\n<]*(?:</system\s*>)?",
                    after,
                    re.IGNORECASE,
                )
                if footer:
                    close_end += footer.end()
                after = text[close_end:]
                asst = re.search(r"^\s*</assistant\s*>", after, re.IGNORECASE | re.MULTILINE)
                if asst:
                    close_end += asst.end()
            yield open_m.start(), close_end, text[body_start : close_m.start()]
            pos = close_end
        else:
            yield open_m.start(), len(text), text[body_start:]
            break


def strip_tool_block_spans(text: str) -> str:
    """移除 ``<tool>…`` 块（含误用的 ``</system>`` / ``</assistant>`` 闭合）。"""
    if not text or "<tool" not in text.lower():
        return text
    parts: List[str] = []
    last = 0
    for open_start, close_end, _body in _iter_tool_block_spans(text):
        parts.append(text[last:open_start])
        last = close_end
    parts.append(text[last:])
    out = "".join(parts)
    out = re.sub(r"^\s*<assistant\s*>\s*\n+", "", out, count=1, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


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
    if isinstance(value, str):
        args = _args_from_scalar(name, value, schema_index)
    else:
        args = _args_from_parsed(name, value)
    args = coerce_entml_arguments(args, name, schema_index)
    return [(name, args)]


def _parse_mangled_brace_entml_params(
    body: str,
    known: Set[str],
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """``<tool>\\n{Bash>\\n<entml:parameter>...`` 混合格式。"""
    match = _MANGLED_BRACE_ENTML_HEAD_RE.search(body)
    if not match:
        return []
    name = normalize_entml_name(match.group(1))
    if known and name not in known:
        return []
    rest = body[match.end() :].lstrip()
    if not _PARAM_MARKER_RE.search(rest):
        return []
    from .entml_invoke import parse_invoke_args

    args = parse_invoke_args(rest, name, schema_index)
    if not args:
        return []
    args = coerce_entml_arguments(args, name, schema_index)
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

    mangled = _parse_mangled_brace_entml_params(text, known, schema_index)
    if mangled:
        return mangled

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
    for _open, _close, body in _iter_tool_block_spans(text):
        for name, args in parse_tool_block_body(
            body,
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
