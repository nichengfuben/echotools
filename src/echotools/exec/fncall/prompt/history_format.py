from __future__ import annotations

"""Conversation history block formatting."""

from typing import Any, Dict, List, Optional

from echotools.exec.fncall.shared.normalization import normalize_content

from .prompt_helpers import (
    format_assistant_block,
    format_assistant_block_with_results,
    format_tool_block,
    format_user_block,
    join_history_parts,
)


def _format_conversation_history(
    messages: List[Dict[str, Any]],
    protocol: Optional[Any] = None,
    *,
    include_thinking_in_history: bool = False,
) -> str:
    if not messages:
        return ""

    call_id_to_name: Dict[str, str] = {}
    seen_assistant_keys = set()
    parts: List[tuple] = []
    clean_fn = protocol.clean_tags if protocol and hasattr(protocol, "clean_tags") else None

    i = 0
    while i < len(messages):
        m = messages[i]
        role: str = m.get("role") or "user"
        content_str = normalize_content(m.get("content", ""))

        if role == "user":
            parts.append((format_user_block(content_str, clean_fn), False))
            i += 1
            continue

        if role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                # collect immediately following tool messages
                tool_msgs = []
                j = i + 1
                while j < len(messages) and (messages[j].get("role") or "user") == "tool":
                    tool_msgs.append(messages[j])
                    j += 1
                block = format_assistant_block_with_results(
                    m, tool_msgs, protocol, call_id_to_name, seen_assistant_keys,
                    include_thinking_in_history=include_thinking_in_history,
                )
                if block:
                    parts.append((block, False))
                i = j
            else:
                block = format_assistant_block(
                    m, content_str, protocol, call_id_to_name, seen_assistant_keys,
                    include_thinking_in_history=include_thinking_in_history,
                )
                if block:
                    parts.append((block, False))
                i += 1
            continue

        if role == "tool":
            # orphan tool message (not consumed above)
            parts.append((format_tool_block(m, content_str, call_id_to_name), True))
            i += 1
            continue

        parts.append((f"<{role}>\n{content_str}\n</{role}>", False))
        i += 1

    return join_history_parts(parts)
