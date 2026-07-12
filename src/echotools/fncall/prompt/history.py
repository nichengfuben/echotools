"""对话历史格式化和消息规范化。

从 src/core/tools.py 迁移（原 lines 846-1164）。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

from echotools.fncall.shared.normalization import normalize_content
from echotools.logger.manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 正则常量（伪格式检测与转换）
# ---------------------------------------------------------------------------

_TOOL_CALL_LINE_RE = re.compile(
    r"^Tool call \(([^)]+)\)\s*:\s*(\w[\w.]*)\((\{.*?\})\)\s*$",
    re.MULTILINE | re.DOTALL,
)
_TOOL_CALL_ID_RE = re.compile(
    r"Tool call \(([^)]+)\)\s*:",
)
_TOOL_RESULT_LINE_RE = re.compile(
    r"^Tool result \(([^)]+)\)\s*:\s*",
)

_TOOL_CALL_MARKER_RE = re.compile(
    r"<function_calls|<antml:function_calls|\[function_calls\]"
    r'|<\|PROVIDER\|tool_calls|"type"\s*:\s*"function_call"'
    r"|<invoke\s+name=",
)

# entml 标签清理正则
_ENTML_FNCALL_BLOCK_RE = re.compile(
    r"<entml:function_calls\b[^>]*>.*?</entml:function_calls>",
    re.DOTALL,
)
_ENTML_INVOKE_RE = re.compile(
    r'<entml:invoke\s+name="[^"]+"\s*>.*?</entml:invoke>',
    re.DOTALL,
)
_ENTML_PARAMETERS_RE = re.compile(
    r'<entml:parameters>.*?</entml:parameters>',
    re.DOTALL,
)
_ENTML_PARAM_RE = re.compile(
    r'<entml:parameter\s+name="[^"]+"\s*>.*?</entml:parameter>',
    re.DOTALL,
)
# 清理任意 entml:* 标签
_ENTML_ANY_TAG_RE = re.compile(
    r'<entml:[a-zA-Z_][\w]*\b[^>]*>.*?</entml:[a-zA-Z_][\w]*>',
    re.DOTALL,
)


def _clean_entml_tags(content: str) -> str:
    """移除内容中的所有 entml 标签及其内部内容。"""
    if not content:
        return content
    cleaned = content
    cleaned = _ENTML_FNCALL_BLOCK_RE.sub("", cleaned)
    cleaned = _ENTML_INVOKE_RE.sub("", cleaned)
    cleaned = _ENTML_PARAMETERS_RE.sub("", cleaned)
    cleaned = _ENTML_PARAM_RE.sub("", cleaned)
    cleaned = _ENTML_ANY_TAG_RE.sub("", cleaned)
    # 清理多余空行
    lines = [line for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 渲染工具调用 / 工具结果
# ---------------------------------------------------------------------------


def _render_parameter_value(v: Any) -> str:
    """将参数值渲染为适合嵌入 XML parameter 标签的字符串。"""
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def _render_tool_call(tc: Dict[str, Any]) -> str:
    """将单个 tool_call 对象渲染为 function_calls XML 块。"""
    fn: Dict[str, Any] = tc.get("function") or {}
    name: str = fn.get("name") or ""
    args_str: str = fn.get("arguments") or "{}"

    try:
        args_dict = json.loads(args_str)
        if not isinstance(args_dict, dict):
            args_dict = {"value": args_dict}
    except json.JSONDecodeError:
        logger.debug(
            "_render_tool_call: arguments 非合法 JSON，原样传递: %r",
            args_str[:200],
        )
        args_dict = {"value": args_str}

    lines: List[str] = ["<function_calls>", f'<invoke name="{name}">']
    for k, v in args_dict.items():
        val = _render_parameter_value(v).strip("\n")
        lines.append(f'<parameter name="{k}">{val}</parameter>')
    lines.append("</invoke>")
    lines.append("</function_calls>")
    return "\n".join(lines)


def _render_tool_result(
    content: Any,
    tool_name: str = "",
    is_error: bool = False,
) -> str:
    """将工具执行结果渲染为 function_results XML 块。"""
    text = normalize_content(content)
    lines: List[str] = ["<function_results>", "<result>"]
    if tool_name:
        lines.append(f"<tool_name>{tool_name}</tool_name>")
    if is_error:
        lines.append("<is_error>true</is_error>")
    lines.append("<stdout>")
    lines.append(text)
    lines.append("</stdout>")
    lines.append("</result>")
    lines.append("</function_results>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 伪格式检测与转换
# ---------------------------------------------------------------------------


def _strip_tool_result_prefix(content: str) -> str:
    """剥离 content 开头的 'Tool result (id): ' 前缀。"""
    m = _TOOL_RESULT_LINE_RE.match(content)
    if m:
        return content[m.end():].lstrip("\n")
    return content


def _parse_pseudo_tool_calls(
    content: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """解析 assistant 消息中的 Tool call 伪格式行。"""
    tool_calls: List[Dict[str, Any]] = []
    kept_lines: List[str] = []

    for line in content.splitlines():
        m = _TOOL_CALL_LINE_RE.match(line.strip())
        if m:
            tool_id = m.group(1).strip()
            func_name = m.group(2).strip()
            args_raw = m.group(3).strip()
            try:
                args_obj = json.loads(args_raw)
                if not isinstance(args_obj, dict):
                    args_obj = {"value": args_obj}
                arguments = json.dumps(args_obj, ensure_ascii=False)
            except json.JSONDecodeError:
                logger.debug(
                    "_parse_pseudo_tool_calls: 参数非合法 JSON: %r",
                    args_raw[:200],
                )
                arguments = "{}"
            tool_calls.append(
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                }
            )
        else:
            kept_lines.append(line)

    cleaned = "\n".join(kept_lines).strip()
    return cleaned, tool_calls


def _collect_tool_call_ids(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    """扫描所有 assistant 消息，收集 tool_id -> tool_name 映射。"""
    id_to_name: Dict[str, str] = {}

    for msg in messages:
        if (msg.get("role") or "user") != "assistant":
            continue

        for tc in msg.get("tool_calls") or []:
            tid: str = tc.get("id") or ""
            fn_name: str = (tc.get("function") or {}).get("name") or ""
            if tid:
                id_to_name.setdefault(tid, fn_name)

        content_str = normalize_content(msg.get("content", ""))
        if not content_str:
            continue

        for line in content_str.splitlines():
            stripped = line.strip()
            m_full = _TOOL_CALL_LINE_RE.match(stripped)
            if m_full:
                tid = m_full.group(1).strip()
                fn_name = m_full.group(2).strip()
                if tid:
                    id_to_name.setdefault(tid, fn_name)
                continue
            m_id = _TOOL_CALL_ID_RE.search(stripped)
            if m_id:
                tid = m_id.group(1).strip()
                if tid:
                    id_to_name.setdefault(tid, "")

    return id_to_name


@lru_cache(maxsize=256)
def _parse_tool_result_info(content: str) -> Optional[Tuple[str, str]]:
    """从消息内容中解析 tool result 前缀，返回 (tool_id, clean_content)。"""
    if not content:
        return None

    first_line = ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break

    if not first_line:
        return None

    m = _TOOL_RESULT_LINE_RE.match(first_line)
    if not m:
        return None

    tool_id = m.group(1).strip()
    clean = _strip_tool_result_prefix(content)
    return (tool_id, clean)


def _try_convert_user_to_tool(
    message: Dict[str, Any],
    known_tool_ids: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """尝试将 user 消息转换为标准 tool 角色消息。"""
    content_str = normalize_content(message.get("content", ""))
    parsed = _parse_tool_result_info(content_str)
    if parsed is None:
        return None

    tool_id, clean_content = parsed
    if tool_id not in known_tool_ids:
        return None

    return {
        "role": "tool",
        "tool_call_id": tool_id,
        "content": clean_content,
    }


def _convert_assistant_pseudo_calls(message: Dict[str, Any]) -> Dict[str, Any]:
    """将 assistant 消息中的 Tool call 伪格式转换为标准 tool_calls 结构。"""
    if message.get("tool_calls"):
        return message

    content_str = normalize_content(message.get("content", ""))
    if not content_str:
        return message

    cleaned, tool_calls = _parse_pseudo_tool_calls(content_str)
    if not tool_calls:
        return message

    new_msg = dict(message)
    new_msg["content"] = cleaned or None
    new_msg["tool_calls"] = tool_calls
    return new_msg


def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对消息列表做预处理：伪格式转换 + 孤立 tool_call 补全。"""
    if not messages:
        return []

    # Step 1: convert pseudo tool calls in assistant messages
    step1: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role") or "user"
        if role == "assistant":
            step1.append(_convert_assistant_pseudo_calls(m))
        else:
            step1.append(m)

    # Step 2: collect known tool_call IDs from assistant messages
    known_tool_ids = _collect_tool_call_ids(step1)
    if not known_tool_ids:
        return step1

    # Step 3: convert user messages that look like tool results
    step2: List[Dict[str, Any]] = []
    for m in step1:
        role = m.get("role") or "user"
        if role == "user":
            converted = _try_convert_user_to_tool(m, known_tool_ids)
            if converted is not None:
                step2.append(converted)
                continue
        step2.append(m)

    # Step 4: detect orphan tool_calls (no corresponding tool result) and inject synthetic results
    existing_tool_ids: Set[str] = set()
    for m in step2:
        if (m.get("role") or "user") == "tool":
            tid = m.get("tool_call_id") or ""
            if tid:
                existing_tool_ids.add(tid)

    result: List[Dict[str, Any]] = []
    for m in step2:
        result.append(m)
        role = m.get("role") or "user"
        if role == "assistant":
            for tc in m.get("tool_calls") or []:
                tid = tc.get("id") or ""
                if tid and tid not in existing_tool_ids:
                    fn_name = (tc.get("function") or {}).get("name") or "unknown"
                    result.append({
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": f"[tool {fn_name} was called but no result was provided]",
                    })
                    existing_tool_ids.add(tid)

    return result


# ---------------------------------------------------------------------------
# 对话历史格式化
# ---------------------------------------------------------------------------


def _make_assistant_dedup_key(
    content: Optional[str],
    tool_calls: List[Dict[str, Any]],
) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
    """生成 assistant 消息的去重键。"""
    safe_content = content or ""
    tc_key: Tuple[Tuple[str, str], ...] = tuple(
        (
            (tc.get("function") or {}).get("name") or "",
            (tc.get("function") or {}).get("arguments") or "",
        )
        for tc in tool_calls
    )
    return (safe_content, tc_key)


def _format_conversation_history(
    messages: List[Dict[str, Any]],
    protocol: Optional[Any] = None,
) -> str:
    """将历史消息列表格式化为对话历史文本块。

    Args:
        messages: 消息列表。
        protocol: 可选的 ToolProtocol 实例。提供时使用
            protocol.format_assistant_tool_calls() 渲染工具调用，
            确保历史中的工具调用格式与 LLM 指令中的格式一致。
            同时使用 protocol.clean_tags() 清理 user 消息中的 entml 标签。

    始终渲染所有消息角色（包括 assistant tool_calls 和 tool results），
    不区分客户端类型。
    """
    if not messages:
        return ""

    call_id_to_name: Dict[str, str] = {}
    seen_assistant_keys: Set[Tuple[str, Tuple[Tuple[str, str], ...]]] = set()
    parts: List[Tuple[str, bool]] = []

    # 获取清理函数
    clean_fn = None
    if protocol and hasattr(protocol, 'clean_tags'):
        clean_fn = protocol.clean_tags

    for m in messages:
        role: str = m.get("role") or "user"
        content_str = normalize_content(m.get("content", ""))

        if role == "user":
            # 清理用户消息中的 entml 标签
            if clean_fn:
                content_str = clean_fn(content_str)
            parts.append((f"<user>\n{content_str}\n</user>", False))

        elif role == "assistant":
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
                content_has_markers = bool(
                    content_str and _TOOL_CALL_MARKER_RE.search(content_str)
                )
                if not content_has_markers:
                    if protocol is not None and hasattr(protocol, 'format_assistant_tool_calls'):
                        blocks.append(protocol.format_assistant_tool_calls(tcs))
                    else:
                        for tc in tcs:
                            blocks.append(_render_tool_call(tc))

            inner = "\n\n".join(blocks)
            if not inner:
                continue
            rendered = f"<assistant>\n{inner}\n</assistant>"

            dedup_key = _make_assistant_dedup_key(content_str, tcs)
            if dedup_key in seen_assistant_keys:
                logger.debug("跳过重复 assistant 消息（dedup_key 已见）")
                continue
            seen_assistant_keys.add(dedup_key)
            parts.append((rendered, False))

        elif role == "tool":
            tid = m.get("tool_call_id") or ""
            tool_name = call_id_to_name.get(tid, "")
            is_error: bool = bool(m.get("is_error", False))
            rendered = _render_tool_result(content_str, tool_name, is_error)
            parts.append((rendered, True))

        else:
            parts.append((f"<{role}>\n{content_str}\n</{role}>", False))

    if not parts:
        return ""

    result_parts: List[str] = [parts[0][0]]
    for text, is_tool in parts[1:]:
        sep = "\n" if is_tool else "\n\n"
        result_parts.append(sep + text)

    return "".join(result_parts)
