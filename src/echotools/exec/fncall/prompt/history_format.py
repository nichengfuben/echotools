from __future__ import annotations

"""Conversation history block formatting."""

from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.shared.normalization import normalize_content

from .prompt_helpers import (
    format_assistant_block,
    format_assistant_block_with_results,
    format_tool_block,
    format_user_block,
    join_history_parts,
)


def history_contains_tool_calls(messages: List[Dict[str, Any]]) -> bool:
    """历史消息中是否包含 assistant tool_calls 或 tool 结果。"""
    for m in messages:
        role = m.get("role") or "user"
        if role == "assistant" and m.get("tool_calls"):
            return True
        if role == "tool":
            return True
    return False


def _append_user_part(
    parts: List[Tuple[str, bool]],
    m: Dict[str, Any],
    clean_fn: Any,
) -> None:
    content_str = normalize_content(m.get("content", ""))
    parts.append((format_user_block(content_str, clean_fn), False))


def _append_assistant_part(
    parts: List[Tuple[str, bool]],
    messages: List[Dict[str, Any]],
    index: int,
    protocol: Optional[Any],
    call_id_to_name: Dict[str, str],
    *,
    include_thinking_in_history: bool,
) -> int:
    m = messages[index]
    content_str = normalize_content(m.get("content", ""))
    tcs = m.get("tool_calls") or []
    if tcs:
        tool_msgs = []
        j = index + 1
        while j < len(messages) and (messages[j].get("role") or "user") == "tool":
            tool_msgs.append(messages[j])
            j += 1
        blocks = format_assistant_block_with_results(
            m, tool_msgs, protocol, call_id_to_name,
            include_thinking_in_history=include_thinking_in_history,
        )
        for block in blocks:
            parts.append((block, False))
        return j

    blocks = format_assistant_block(
        m, content_str, protocol, call_id_to_name,
        include_thinking_in_history=include_thinking_in_history,
    )
    for block in blocks:
        parts.append((block, False))
    return index + 1


def _format_conversation_history(
    messages: List[Dict[str, Any]],
    protocol: Optional[Any] = None,
    *,
    include_thinking_in_history: bool = False,
) -> str:
    if not messages:
        return ""

    call_id_to_name: Dict[str, str] = {}
    parts: List[Tuple[str, bool]] = []
    clean_fn = protocol.clean_tags if protocol and hasattr(protocol, "clean_tags") else None

    i = 0
    while i < len(messages):
        m = messages[i]
        role: str = m.get("role") or "user"

        if role == "user":
            _append_user_part(parts, m, clean_fn)
            i += 1
            continue

        if role == "assistant":
            i = _append_assistant_part(
                parts, messages, i, protocol, call_id_to_name,
                include_thinking_in_history=include_thinking_in_history,
            )
            continue

        if role == "tool":
            content_str = normalize_content(m.get("content", ""))
            parts.append((format_tool_block(m, content_str, call_id_to_name), True))
            i += 1
            continue

        content_str = normalize_content(m.get("content", ""))
        parts.append((f"<{role}>\n{content_str}\n</{role}>", False))
        i += 1

    return join_history_parts(parts)
