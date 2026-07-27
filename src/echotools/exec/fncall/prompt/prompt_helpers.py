from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from echotools.base.logger.manager import get_logger
from echotools.exec.fncall.protocols.entml_think.hist import (
    extract_reasoning_text,
    format_entml_thinking_history_block,
)
from echotools.exec.fncall.shared.normalization import normalize_content

from .history import (
    _TOOL_CALL_MARKER_RE,
    _convert_assistant_pseudo_calls,
    _make_assistant_dedup_key,
    _render_inline_call_result,
    _render_tool_call,
    _render_tool_result,
    _try_convert_user_to_tool,
)

logger = get_logger(__name__)


def _assistant_history_content_blocks(
    m: Dict[str, Any],
    content_str: str,
    protocol: Optional[Any],
    include_thinking_in_history: bool,
) -> List[str]:
    """构建 assistant 历史块正文（可选前置 entml:thinking）。"""
    blocks: List[str] = []
    if (
        include_thinking_in_history
        and protocol is not None
        and getattr(protocol, "id", None) == "entml"
    ):
        reasoning = extract_reasoning_text(m)
        if reasoning:
            thinking_block = format_entml_thinking_history_block(reasoning)
            if thinking_block:
                blocks.append(thinking_block)
    if content_str:
        blocks.append(content_str)
    return blocks


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


def _format_assistant_text_block(
    m: Dict[str, Any],
    content_str: str,
    protocol: Optional[Any],
    *,
    include_thinking_in_history: bool = False,
) -> Optional[str]:
    blocks = _assistant_history_content_blocks(
        m, content_str, protocol, include_thinking_in_history
    )
    if not blocks:
        return None
    body = "\n\n".join(blocks)
    return f"<assistant>\n{body}\n</assistant>"


def _register_tool_call_names(
    tool_calls: List[Dict[str, Any]],
    call_id_to_name: Dict[str, str],
) -> None:
    for tc in tool_calls:
        cid = tc.get("id") or ""
        fn_name = (tc.get("function") or {}).get("name") or ""
        if cid and fn_name:
            call_id_to_name[cid] = fn_name


def _format_tool_turn_block(
    tool_calls: List[Dict[str, Any]],
    tool_msgs: List[Dict[str, Any]],
    protocol: Optional[Any],
) -> Optional[str]:
    if not tool_calls:
        return None

    tid_to_result: Dict[str, Dict[str, Any]] = {
        (tmsg.get("tool_call_id") or ""): tmsg for tmsg in tool_msgs
    }
    turn_fmt = getattr(protocol, "format_assistant_tool_turn_block", None)
    if turn_fmt is not None:
        return turn_fmt(tool_calls, tid_to_result)

    lines: List[str] = []
    for tc in tool_calls:
        if protocol is not None and hasattr(protocol, "format_assistant_tool_calls"):
            call_text = protocol.format_assistant_tool_calls([tc])
        else:
            call_text = _render_tool_call(tc)
        tid = tc.get("id") or ""
        result_msg = tid_to_result.get(tid)
        if result_msg is not None:
            result_content = normalize_content(result_msg.get("content", ""))
            is_error = bool(result_msg.get("is_error", False))
            lines.append(
                _render_inline_call_result(call_text, result_content, is_error)
            )
        else:
            lines.append(call_text)
    return "\n\n".join(lines)


def format_assistant_block(
    m: Dict[str, Any],
    content_str: str,
    protocol: Optional[Any],
    call_id_to_name: Dict[str, str],
    seen_assistant_keys: Set[Tuple[str, Tuple[Tuple[str, str], ...]]],
    *,
    include_thinking_in_history: bool = False,
) -> List[str]:
    tcs: List[Dict[str, Any]] = m.get("tool_calls") or []
    _register_tool_call_names(tcs, call_id_to_name)

    dedup_key = _make_assistant_dedup_key(content_str, tcs)
    if dedup_key in seen_assistant_keys:
        logger.debug("跳过重复 assistant 消息（dedup_key 已见）")
        return []
    seen_assistant_keys.add(dedup_key)

    parts: List[str] = []
    assistant = _format_assistant_text_block(
        m, content_str, protocol, include_thinking_in_history=include_thinking_in_history
    )
    if assistant:
        parts.append(assistant)

    if tcs:
        has_markers = bool(content_str and _TOOL_CALL_MARKER_RE.search(content_str))
        if not has_markers:
            tool_block = _format_tool_turn_block(tcs, [], protocol)
            if tool_block:
                parts.append(tool_block)

    return parts


def format_assistant_block_with_results(
    m: Dict[str, Any],
    tool_msgs: List[Dict[str, Any]],
    protocol: Optional[Any],
    call_id_to_name: Dict[str, str],
    seen_assistant_keys: Set[Tuple[str, Tuple[Tuple[str, str], ...]]],
    *,
    include_thinking_in_history: bool = False,
) -> List[str]:
    tcs: List[Dict[str, Any]] = m.get("tool_calls") or []
    content_str = normalize_content(m.get("content", ""))
    _register_tool_call_names(tcs, call_id_to_name)

    dedup_key = _make_assistant_dedup_key(content_str, tcs)
    if dedup_key in seen_assistant_keys:
        logger.debug("跳过重复 assistant 消息（dedup_key 已见）")
        return []
    seen_assistant_keys.add(dedup_key)

    parts: List[str] = []
    assistant = _format_assistant_text_block(
        m, content_str, protocol, include_thinking_in_history=include_thinking_in_history
    )
    if assistant:
        parts.append(assistant)

    tool_block = _format_tool_turn_block(tcs, tool_msgs, protocol)
    if tool_block:
        parts.append(tool_block)

    return parts


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
