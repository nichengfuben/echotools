from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from echotools.base.logger.manager import get_logger
from echotools.exec.fncall.shared.normalization import normalize_content

from .history import (
    _TOOL_CALL_MARKER_RE,
    _convert_assistant_pseudo_calls,
    _make_assistant_dedup_key,
    _render_tool_call,
    _render_tool_result,
    _try_convert_user_to_tool,
)

logger = get_logger(__name__)


def split_last_user_message(
    normalized: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str]:
    last_user_idx: Optional[int] = None
    for i in range(len(normalized) - 1, -1, -1):
        if (normalized[i].get("role") or "user") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        return normalized, ""
    history = normalized[:last_user_idx] + normalized[last_user_idx + 1 :]
    current = normalize_content(normalized[last_user_idx].get("content", ""))
    return history, current


def build_no_tools_prompt(history_text: str, current_user_message: str) -> str:
    return (
        f"<conversation_history>\n{history_text}\n</conversation_history>\n\n"
        f"<current_user_message>\n{current_user_message}\n</current_user_message>"
    )


def format_user_block(content_str: str, clean_fn: Optional[Any]) -> str:
    if clean_fn:
        content_str = clean_fn(content_str)
    return f"<user>\n{content_str}\n</user>"


def format_assistant_block(
    m: Dict[str, Any],
    content_str: str,
    protocol: Optional[Any],
    call_id_to_name: Dict[str, str],
    seen_assistant_keys: Set[Tuple[str, Tuple[Tuple[str, str], ...]]],
) -> Optional[str]:
    tcs: List[Dict[str, Any]] = m.get("tool_calls") or []
    blocks: List[str] = []
    if content_str:
        blocks.append(content_str)
    for tc in tcs:
        cid = tc.get("id") or ""
        fn_name = (tc.get("function") or {}).get("name") or ""
        if cid and fn_name:
            call_id_to_name[cid] = fn_name
    if tcs:
        has_markers = bool(content_str and _TOOL_CALL_MARKER_RE.search(content_str))
        if not has_markers:
            if protocol is not None and hasattr(protocol, "format_assistant_tool_calls"):
                blocks.append(protocol.format_assistant_tool_calls(tcs))
            else:
                blocks.extend(_render_tool_call(tc) for tc in tcs)
    inner = "\n\n".join(blocks)
    if not inner:
        return None
    rendered = f"<assistant>\n{inner}\n</assistant>"
    dedup_key = _make_assistant_dedup_key(content_str, tcs)
    if dedup_key in seen_assistant_keys:
        logger.debug("跳过重复 assistant 消息（dedup_key 已见）")
        return None
    seen_assistant_keys.add(dedup_key)
    return rendered


def format_tool_block(
    m: Dict[str, Any], content_str: str, call_id_to_name: Dict[str, str]
) -> str:
    tid = m.get("tool_call_id") or ""
    tool_name = call_id_to_name.get(tid, "")
    is_error = bool(m.get("is_error", False))
    return _render_tool_result(content_str, tool_name, is_error)


def join_history_parts(parts: List[Tuple[str, bool]]) -> str:
    if not parts:
        return ""
    result_parts: List[str] = [parts[0][0]]
    for text, is_tool in parts[1:]:
        result_parts.append(("\n" if is_tool else "\n\n") + text)
    return "".join(result_parts)


def convert_assistant_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    step1: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role") or "user"
        if role == "assistant":
            step1.append(_convert_assistant_pseudo_calls(m))
        else:
            step1.append(m)
    return step1


def convert_user_tool_results(
    messages: List[Dict[str, Any]], known_tool_ids: Set[str]
) -> List[Dict[str, Any]]:
    step2: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role") or "user"
        if role == "user":
            converted = _try_convert_user_to_tool(m, known_tool_ids)
            if converted is not None:
                step2.append(converted)
                continue
        step2.append(m)
    return step2


def inject_orphan_tool_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing_tool_ids: Set[str] = set()
    for m in messages:
        if (m.get("role") or "user") == "tool":
            tid = m.get("tool_call_id") or ""
            if tid:
                existing_tool_ids.add(tid)

    result: List[Dict[str, Any]] = []
    for m in messages:
        result.append(m)
        role = m.get("role") or "user"
        if role != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            tid = tc.get("id") or ""
            if not tid or tid in existing_tool_ids:
                continue
            fn_name = (tc.get("function") or {}).get("name") or "unknown"
            result.append({
                "role": "tool",
                "tool_call_id": tid,
                "content": f"[tool {fn_name} was called but no result was provided]",
            })
            existing_tool_ids.add(tid)
    return result
