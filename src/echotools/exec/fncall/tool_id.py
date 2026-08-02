"""Tool call id 生成与规范化（Anthropic ``toolu_`` 约定）。"""

from __future__ import annotations

from typing import Any, Dict

from echotools.base.ids.generator import gen_tool_id

_PLACEHOLDER_EXACT = frozenset({"", "call_0000", "toolu_call_0001"})
_PLACEHOLDER_PREFIXES = ("call_", "toolu_call_")


def is_placeholder_tool_call_id(raw_id: str) -> bool:
    """echotools 解析占位 id（``call_0000`` / ``toolu_call_*`` 等）应视为无效。"""
    if not raw_id or raw_id in _PLACEHOLDER_EXACT:
        return True
    return raw_id.startswith(_PLACEHOLDER_PREFIXES)


def ensure_toolu_tool_call_id(raw_id: str) -> str:
    """占位 id 换新；已有 id 无 ``toolu_`` 前缀则补上（Anthropic tool_use 输出）。"""
    tid = (raw_id or "").strip()
    if is_placeholder_tool_call_id(tid):
        return gen_tool_id()
    if not tid.startswith("toolu_"):
        return f"toolu_{tid}"
    return tid


def fix_tool_call_id(tc: Dict[str, Any]) -> Dict[str, Any]:
    """将 OpenAI 格式 tool call 的占位 id 替换为 ``gen_tool_id()`` 结果。"""
    raw_id = str(tc.get("id") or "")
    call_id = gen_tool_id() if is_placeholder_tool_call_id(raw_id) else raw_id
    func = tc.get("function") or {}
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": func.get("name", ""),
            "arguments": func.get("arguments", "{}"),
        },
    }
