"""Agent 循环检测。

从 src/core/tools.py 迁移（原 lines 513-609）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


class LoopDetectionResult:
    """循环检测结果。"""

    __slots__ = ("is_looping", "repeat_count", "fingerprint", "suggestion")

    def __init__(
        self,
        is_looping: bool,
        repeat_count: int,
        fingerprint: str,
        suggestion: str,
    ) -> None:
        self.is_looping = is_looping
        self.repeat_count = repeat_count
        self.fingerprint = fingerprint
        self.suggestion = suggestion

    def __repr__(self) -> str:
        return (
            f"LoopDetectionResult(is_looping={self.is_looping}, "
            f"repeat_count={self.repeat_count}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _tool_call_fingerprint(tool_calls: List[Dict[str, Any]]) -> str:
    """生成一次 assistant 调用的指纹字符串。"""
    if not tool_calls:
        return ""

    parts: List[str] = []
    for tc in sorted(
        tool_calls,
        key=lambda x: (x.get("function") or {}).get("name") or "",
    ):
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        args = fn.get("arguments") or "{}"
        try:
            args_normalized = json.dumps(
                json.loads(args), sort_keys=True, ensure_ascii=False
            )
        except (json.JSONDecodeError, TypeError):
            args_normalized = args
        parts.append(f"{name}:{args_normalized}")

    combined = "|".join(parts)
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:16]  # noqa: S324


def detect_tool_loop(
    messages: List[Dict[str, Any]],
    threshold: int = 3,
) -> LoopDetectionResult:
    """检测 agent loop 中的重复工具调用循环。"""
    fingerprints: List[str] = []

    for msg in messages:
        if (msg.get("role") or "") != "assistant":
            continue
        tcs: List[Dict[str, Any]] = msg.get("tool_calls") or []
        fp = _tool_call_fingerprint(tcs)
        if fp:
            fingerprints.append(fp)

    if not fingerprints:
        return LoopDetectionResult(False, 0, "", "")

    last_fp = fingerprints[-1]
    count = 0
    for fp in reversed(fingerprints):
        if fp == last_fp:
            count += 1
        else:
            break

    if count >= threshold:
        suggestion = (
            "You appear to be in a loop making the same tool call repeatedly "
            f"({count} times). Stop, reassess your approach, and try a "
            "different strategy or report that you cannot complete the task."
        )
        return LoopDetectionResult(True, count, last_fp, suggestion)

    return LoopDetectionResult(False, count, last_fp, "")


import re as _re

_CDATA_RE = _re.compile(r'<!\[CDATA\[([\s\S]*?)\]\]>')
_XML_ESCAPE_MAP = {
    '&': '&amp;',
    '"': '&quot;',
    "'": '&apos;',
    '<': '&lt;',
    '>': '&gt;',
}


def extract_cdata(value: str) -> str:
    cdata = _CDATA_RE.search(value)
    if cdata:
        return cdata.group(1).strip()
    return value.strip()


def escape_xml_attr(value: str) -> str:
    for char, escape in _XML_ESCAPE_MAP.items():
        value = value.replace(char, escape)
    return value


_PROVIDER_BLOCK_RE = _re.compile(
    r'<\|PROVIDER\|tool_calls>([\s\S]*?)</\|PROVIDER\|tool_calls>',
    _re.DOTALL,
)
_PROVIDER_INVOKE_RE = _re.compile(
    r'<\|PROVIDER\|invoke\s+name="([^"]+)"\s*>([\s\S]*?)</\|PROVIDER\|invoke>',
    _re.DOTALL,
)
_PROVIDER_PARAM_RE = _re.compile(
    r'<\|PROVIDER\|parameter\s+name="([^"]+)"\s*>([\s\S]*?)</\|PROVIDER\|parameter>',
    _re.DOTALL,
)
