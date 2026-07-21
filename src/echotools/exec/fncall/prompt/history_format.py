from __future__ import annotations

"""Conversation history block formatting."""

from typing import Any, Dict, List, Optional

from echotools.exec.fncall.shared.normalization import normalize_content

from .prompt_helpers import (
    build_no_tools_prompt,
    convert_assistant_messages,
    convert_user_tool_results,
    format_assistant_block,
    format_tool_block,
    format_user_block,
    inject_orphan_tool_results,
    join_history_parts,
    split_last_user_message,
)


def _format_conversation_history(
    messages: List[Dict[str, Any]],
    protocol: Optional[Any] = None,
) -> str:
    if not messages:
        return ""

    call_id_to_name: Dict[str, str] = {}
    seen_assistant_keys = set()
    parts: List[tuple] = []
    clean_fn = protocol.clean_tags if protocol and hasattr(protocol, "clean_tags") else None

    for m in messages:
        role: str = m.get("role") or "user"
        content_str = normalize_content(m.get("content", ""))

        if role == "user":
            parts.append((format_user_block(content_str, clean_fn), False))
            continue

        if role == "assistant":
            block = format_assistant_block(
                m, content_str, protocol, call_id_to_name, seen_assistant_keys
            )
            if block:
                parts.append((block, False))
            continue

        if role == "tool":
            parts.append((format_tool_block(m, content_str, call_id_to_name), True))
            continue

        parts.append((f"<{role}>\n{content_str}\n</{role}>", False))

    return join_history_parts(parts)
