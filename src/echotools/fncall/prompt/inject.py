from __future__ import annotations

"""协议感知 fncall 注入（无全局配置）。"""

import os
from typing import Any, Dict, List, Optional

from echotools.fncall.prompt.history import (
    _format_conversation_history,
    _normalize_messages,
)
from echotools.fncall.shared.loop_detect import detect_tool_loop
from echotools.fncall.shared.normalization import (
    format_tool_descs,
    normalize_content,
)
from echotools.ids.generator import uuid7
from echotools.logger.manager import get_logger
from echotools.protocol.base import ToolProtocol

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


def inject_fncall(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    protocol: ToolProtocol,
    lang: str = "en",
    user_system_prompt: str = "",
    loop_detection_threshold: int = 3,
    dump_prompt: bool = False,
    dump_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """注入工具定义为单条 user 消息。

    Args:
        messages: 消息列表。
        tools: 工具定义。
        protocol: 协议实例。
        lang: 语言。
        user_system_prompt: 用户系统提示。
        loop_detection_threshold: 循环检测阈值，0 关闭。
        dump_prompt: 是否转储。
        dump_dir: 转储目录。

    Returns:
        单条 user 消息列表。
    """
    if not tools:
        return list(messages)
    normalized = _normalize_messages(list(messages))
    loop_warning = ""
    if loop_detection_threshold > 0:
        result = detect_tool_loop(normalized, loop_detection_threshold)
        if result.is_looping:
            logger.debug(
                "检测到工具循环（%d 次）", result.repeat_count
            )
            loop_warning = result.suggestion
    last_user_idx: Optional[int] = None
    for i in range(len(normalized) - 1, -1, -1):
        if (normalized[i].get("role") or "user") == "user":
            last_user_idx = i
            break
    if last_user_idx is not None:
        history_messages = (
            normalized[:last_user_idx]
            + normalized[last_user_idx + 1 :]
        )
        current_user_message = normalize_content(
            normalized[last_user_idx].get("content", "")
        )
    else:
        history_messages = normalized
        current_user_message = ""
    if hasattr(protocol, 'format_tool_descs'):
        tool_descs = protocol.format_tool_descs(tools)
    else:
        tool_descs = format_tool_descs(tools)
    history_text = _format_conversation_history(
        history_messages, protocol=protocol
    ).strip()
    prompt = protocol.render_prompt(
        tool_descs=tool_descs,
        lang=lang,
        user_system_prompt=user_system_prompt,
        history_text=history_text,
        loop_warning=loop_warning,
        current_user_message=current_user_message,
    )
    if dump_prompt:
        _maybe_dump_prompt(prompt, dump_dir)
    return [{"role": "user", "content": prompt}]
