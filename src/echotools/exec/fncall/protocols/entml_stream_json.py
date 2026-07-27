from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .entml_patterns import extract_attr_value, normalize_entml_name

_PARAM_OPEN_RE = re.compile(r"<entml:parameter\b([^>]*)>", re.IGNORECASE)
_PARAM_CLOSE = "</entml:parameter>"
_INVOKE_CLOSE = "</entml:invoke>"
_INVOKE_OPEN_PREFIX = "<entml:invoke"


def _strip_incomplete_markup_suffix(value: str) -> str:
    lt = value.rfind("<")
    if lt < 0:
        return value
    tail = value[lt:]
    for tag in (_PARAM_CLOSE, _INVOKE_CLOSE):
        if tag.startswith(tail) and tail != tag:
            return value[:lt]
    return value


def split_invoke_open(buffer: str) -> Optional[Tuple[str, int]]:
    search_from = 0
    prefix_len = len(_INVOKE_OPEN_PREFIX)
    while True:
        pos = buffer.find(_INVOKE_OPEN_PREFIX, search_from)
        if pos < 0:
            return None
        gt = buffer.find(">", pos + prefix_len)
        if gt < 0:
            return None
        attrs = buffer[pos + prefix_len : gt]
        name = extract_attr_value(attrs, "name")
        if name and normalize_entml_name(name):
            return normalize_entml_name(name), gt + 1
        search_from = gt + 1


def _json_string_body(value: str) -> str:
    """JSON 字符串内部片段（不含外围引号）。"""
    return json.dumps(value, ensure_ascii=False)[1:-1]


def _parse_parameter_entries(body: str) -> List[Tuple[str, str, bool]]:
    """返回 [(key, value, is_complete), ...]。"""
    if not body:
        return []
    entries: List[Tuple[str, str, bool]] = []
    i = 0
    while i < len(body):
        match = _PARAM_OPEN_RE.search(body, i)
        if not match:
            break
        attrs = match.group(1) or ""
        pname = extract_attr_value(attrs, "name")
        if not pname:
            i = match.end()
            continue
        key = normalize_entml_name(pname)
        val_start = match.end()
        close = body.find(_PARAM_CLOSE, val_start)
        if close < 0:
            entries.append((key, _strip_incomplete_markup_suffix(body[val_start:]), False))
            break
        entries.append((key, body[val_start:close], True))
        i = close + len(_PARAM_CLOSE)
    return entries


def build_streaming_json_snapshot(body: str) -> str:
    """构造当前应已发出的 partial_json 累积串（可未完成）。

    仅在 ``</entml:invoke>`` 出现后才闭合最外层 ``}``，避免多参数时
    中间态变成完整 JSON 对象，导致后续 delta 拼接出现 Extra data。
    """
    invoke_closed = _INVOKE_CLOSE in body
    inner = body[: body.index(_INVOKE_CLOSE)] if invoke_closed else body
    entries = _parse_parameter_entries(inner)
    if not entries:
        return ""

    parts: List[str] = ["{"]
    for idx, (key, value, is_complete) in enumerate(entries):
        if idx > 0:
            parts.append(", ")
        parts.append(json.dumps(key, ensure_ascii=False))
        parts.append(": ")
        parts.append('"')
        parts.append(_json_string_body(value))
        if is_complete:
            parts.append('"')
        else:
            return "".join(parts)

    if invoke_closed:
        parts.append("}")
    return "".join(parts)


def _parse_partial_parameter_body(body: str) -> Dict[str, Any]:
    obj: Dict[str, Any] = {}
    for key, value, is_complete in _parse_parameter_entries(
        body[: body.index(_INVOKE_CLOSE)] if _INVOKE_CLOSE in body else body
    ):
        if is_complete or value:
            obj[key] = value
    return obj


def encode_streaming_invoke_json(body: str) -> str:
    obj = _parse_partial_parameter_body(body)
    if not obj:
        return ""
    return json.dumps(obj, ensure_ascii=False)


class EntmlInvokeJsonStreamEncoder:
    """invoke 开标签之后，将 growing body 编码为可拼接的 partial_json 增量。"""

    def __init__(self) -> None:
        self._emitted = ""

    def poll(self, body: str) -> str:
        snapshot = build_streaming_json_snapshot(body)
        if not snapshot.startswith(self._emitted):
            common = 0
            for a, b in zip(self._emitted, snapshot):
                if a != b:
                    break
                common += 1
            delta = snapshot[common:]
            self._emitted = snapshot
            return delta
        delta = snapshot[len(self._emitted) :]
        self._emitted = snapshot
        return delta

    def reset(self) -> None:
        self._emitted = ""
