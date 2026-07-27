from __future__ import annotations

"""协议感知 fncall 注入（无全局配置）。"""

import os
from typing import Any, Dict, List, Optional

from echotools.base.ids.generator import uuid7
from echotools.base.logger.manager import get_logger
from echotools.exec.fncall.prompt.history import (
    _normalize_messages,
)
from echotools.exec.fncall.prompt.history_format import (
    _format_conversation_history,
    history_contains_tool_calls,
)
from echotools.exec.fncall.prompt.prompt_helpers import (
    build_no_tools_prompt,
    split_last_user_message,
)
from echotools.exec.fncall.protocols.entml import (
    format_entml_conversation_history,
    format_entml_current_user_message,
)
from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_section,
)
from echotools.exec.fncall.protocols.entml_think.hist import (
    apply_thinking_history_policy,
    parse_include_thinking_in_history,
)
from echotools.exec.fncall.shared.loop_detect import detect_tool_loop
from echotools.exec.fncall.shared.normalization import (
    format_tool_descs,
    normalize_content,
)
from echotools.exec.protocol.base import ToolProtocol

__all__ = ["inject_fncall"]

logger = get_logger(__name__)


def _maybe_dump_prompt(
    prompt: str, dump_dir: Optional[str]
) -> None:
    """按需转储 prompt。"""
    if not dump_dir:
        return
    try:
        os.makedirs(dump_dir, exist_ok=True)
        path = os.path.join(dump_dir, "{}.txt".format(uuid7()))
        with open(path, "w", encoding="utf-8") as f:
            f.write(prompt)
        logger.debug("prompt 已写入 %s", path)
    except Exception as exc:
        logger.warning("写入 prompt 失败: %s", exc)


def build_tools_prompt(
    protocol: ToolProtocol,
    tools: List[Dict[str, Any]],
    normalized: List[Dict[str, Any]],
    lang: str,
    user_system_prompt: str,
    history_text: str,
    current_user_message: str,
    loop_detection_threshold: int,
    protocol_options: Optional[Dict[str, Any]] = None,
    history_has_tool_calls: bool = False,
) -> str:
    loop_warning = ""
    if loop_detection_threshold > 0:
        result = detect_tool_loop(normalized, loop_detection_threshold)
        if result.is_looping:
            logger.debug("检测到工具循环（%d 次）", result.repeat_count)
            loop_warning = result.suggestion
    if hasattr(protocol, "format_tool_descs"):
        tool_descs = protocol.format_tool_descs(tools)
    else:
        tool_descs = format_tool_descs(tools)
    extra = (
        {"protocol_options": protocol_options}
        if protocol_options is not None and protocol.id == "entml"
        else {}
    )
    if protocol.id == "entml":
        extra["history_has_tool_calls"] = history_has_tool_calls
    return protocol.render_prompt(
        tool_descs=tool_descs,
        lang=lang,
        user_system_prompt=user_system_prompt,
        history_text=history_text,
        loop_warning=loop_warning,
        current_user_message=current_user_message,
        **extra,
    )


def _strip_entml_from_user_messages(
    messages: List[Dict[str, Any]],
    protocol: ToolProtocol,
) -> List[Dict[str, Any]]:
    """从全部 user 消息正文中剥离 entml:* 标签。"""
    clean_fn = getattr(protocol, "clean_tags", None)
    if clean_fn is None:
        return messages
    stripped: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role") or "user"
        if role != "user":
            stripped.append(m)
            continue
        content = normalize_content(m.get("content", ""))
        cleaned = clean_fn(content)
        if cleaned == content:
            stripped.append(m)
        else:
            stripped.append({**m, "content": cleaned})
    return stripped


def inject_fncall(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    protocol: ToolProtocol,
    lang: str = "en",
    user_system_prompt: str = "",
    loop_detection_threshold: int = 3,
    dump_prompt: bool = False,
    dump_dir: Optional[str] = None,
    protocol_options: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """注入工具定义，返回单条 user 消息（含历史）。"""
    include_history = parse_include_thinking_in_history(protocol_options)
    prepared = apply_thinking_history_policy(list(messages), include_history)
    normalized = _normalize_messages(prepared)
    normalized = _strip_entml_from_user_messages(normalized, protocol)
    history_messages, current_user_message = split_last_user_message(normalized)

    history_text = _format_conversation_history(
        history_messages,
        protocol=protocol,
        include_thinking_in_history=include_history,
    ).strip()

    if not tools:
        if protocol.id == "entml":
            sections: List[str] = []
            if history_text.strip():
                sections.append(format_entml_conversation_history(history_text))
            sections.append(format_entml_current_user_message(current_user_message))
            # thinking 放在最后，超限截断时优先保留在 send_text 尾部
            thinking_section = build_entml_thinking_section(protocol_options)
            if thinking_section:
                sections.append(thinking_section)
            prompt = "\n\n".join(sections)
        else:
            prompt = build_no_tools_prompt(history_text, current_user_message)
        if dump_prompt:
            _maybe_dump_prompt(prompt, dump_dir)
        return [{"role": "user", "content": prompt}]

    prompt = build_tools_prompt(
        protocol, tools, normalized, lang, user_system_prompt,
        history_text, current_user_message, loop_detection_threshold, protocol_options,
        history_has_tool_calls=history_contains_tool_calls(history_messages),
    )
    if dump_prompt:
        _maybe_dump_prompt(prompt, dump_dir)
    return [{"role": "user", "content": prompt}]
