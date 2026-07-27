"""Entropy ML (entml) 协议实现。

- 工具调用：<entml:function_calls> / <entml:invoke> / <entml:parameter>
- 对话历史：<entml:conversation_history>
- 当前用户消息：<current_user_message>
"""

from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_TOOL_INVOKE_REMINDER_EN,
)
from echotools.exec.fncall.protocols.entml_invoke import (
    format_entml_tool_calls,
    parse_entml_tool_calls,
)
from echotools.exec.fncall.protocols.entml_patterns import BLOCK_RE
from echotools.exec.fncall.protocols.entml_thinking import build_entml_thinking_section
from echotools.exec.fncall.protocols.entml_tools import format_entml_tool_descs
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.normalization import (
    normalize_content,
    normalize_tool_calls,
)
from echotools.exec.protocol.base import ToolProtocol


def _parse_tool_call_args(tc: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    fn = tc.get("function") or {}
    name = fn.get("name") or ""
    args_str = fn.get("arguments") or "{}"
    try:
        args = _json.loads(args_str) if isinstance(args_str, str) else args_str
        if not isinstance(args, dict):
            args = {"value": args}
    except (_json.JSONDecodeError, TypeError):
        args = {"value": args_str}
    return name, args


def _render_tool_call_line(name: str, args: Dict[str, Any]) -> str:
    """将单次工具调用渲染为紧凑行，例如 [get_weather: 杭州 |c ]。"""
    values: List[str] = []
    for v in args.values():
        if isinstance(v, str):
            values.append(v)
        else:
            values.append(_json.dumps(v, ensure_ascii=False))
    if values:
        return f"[{name}: {values[0]}" + "".join(f" |{v}" for v in values[1:]) + " ]"
    return f"[{name}: ]"


def _render_tool_history_block(body: str) -> str:
    """将工具轮次正文包裹为 <tool> 块。"""
    return f"<tool>\n{body.strip()}\n</tool>"


_ENTML_INSTRUCTION = """\
In this environment you have access to a set of tools you can use to answer the user's question.
You can invoke functions by writing an invoke block like the following as part of your reply to the user:

<entml:invoke name="$FUNCTION_NAME">
<entml:parameter name="$PARAMETER_NAME">$PARAMETER_VALUE</entml:parameter>
...
</entml:invoke>
<entml:invoke name="$FUNCTION_NAME2">
...
</entml:invoke>

String and scalar parameters should be specified as is, while lists and objects should use JSON format.

Here are the functions available in JSONSchema format:
"""


def format_entml_conversation_history(
    history_text: str,
    clarify: str = "",
) -> str:
    """将对话历史正文包裹为 <entml:conversation_history> 块。"""
    if not (history_text or "").strip():
        return ""
    body = history_text.strip()
    if clarify:
        body = f"{clarify}\n\n{body}"
    return (
        f"<entml:conversation_history>\n{body}\n</entml:conversation_history>"
    )


def format_entml_current_user_message(message: str) -> str:
    """将当前用户消息包裹为 <current_user_message> 块。"""
    text = (message or "").strip()
    return f"<current_user_message>\n{text}\n</current_user_message>"


class EntmlProtocol(ToolProtocol):
    """Entropy ML (entml) 格式工具调用协议适配器。"""

    @property
    def id(self) -> str:
        return "entml"

    _TRIGGER = "<entml:invoke>"
    _TRIGGER_PREFIX = "<entml:invoke"

    def get_trigger_tags(self) -> List[str]:
        # 同时声明带/不带 ``>`` 的形式，便于流式 holdback 覆盖属性段
        return [self._TRIGGER, self._TRIGGER_PREFIX]

    def get_stream_end_tags(self) -> List[str]:
        """新格式无外层 wrapper，不自动关闭流，由 finalize() 统一解析。"""
        return []

    @staticmethod
    def format_tool_descs(tools: List[Dict[str, Any]]) -> str:
        return format_entml_tool_descs(tools)

    def render_prompt(
        self,
        tool_descs: str,
        lang: str,
        user_system_prompt: str = "",
        history_text: str = "",
        loop_warning: str = "",
        current_user_message: str = "",
        protocol_options: Optional[Dict[str, Any]] = None,
        history_has_tool_calls: bool = False,
    ) -> str:
        if tool_descs:
            sections: List[str] = [
                _ENTML_INSTRUCTION.rstrip() + "\n\n" + tool_descs
            ]
        else:
            sections = [_ENTML_INSTRUCTION.rstrip()]

        thinking_section = build_entml_thinking_section(protocol_options)
        if thinking_section:
            sections.append(thinking_section)

        if user_system_prompt and user_system_prompt.strip():
            sections.append(
                f"<user_system_prompt>\n{user_system_prompt.strip()}\n</user_system_prompt>"
            )

        if history_text:
            sections.append(
                format_entml_conversation_history(history_text, _HISTORY_CLARIFY_EN)
            )
            if tool_descs and history_has_tool_calls:
                sections.append(_HISTORY_TOOL_INVOKE_REMINDER_EN)

        if loop_warning:
            sections.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")

        sections.append(format_entml_current_user_message(current_user_message))
        return "\n\n".join(sections)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        pos = buffer.find(self._TRIGGER_PREFIX)
        if pos < 0:
            return (False, -1)
        # 确保是完整的开标签（name=" 属性存在）
        close = buffer.find(">", pos + len(self._TRIGGER_PREFIX))
        if close < 0:
            return (False, -1)
        return (True, pos)

    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        schema_index = _build_param_schema_index(tools) if tools else None
        tool_calls = parse_entml_tool_calls(text, tools, schema_index)
        clean = text
        if tool_calls:
            clean = BLOCK_RE.sub("", text).strip()
        return (clean, normalize_tool_calls(tool_calls, tools))

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content: str) -> str:
        return BLOCK_RE.sub("", content).strip()

    def format_assistant_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []
        for tc in tool_calls:
            name, args = _parse_tool_call_args(tc)
            lines.append(_render_tool_call_line(name, args))
        return "\n".join(lines)

    def format_assistant_tool_turn_block(
        self,
        tool_calls: List[Dict[str, Any]],
        tid_to_result: Dict[str, Dict[str, Any]],
    ) -> str:
        """同一 assistant 轮次的全部工具调用与结果合并为一个 <tool> 块。"""
        lines: List[str] = []
        for tc in tool_calls:
            name, args = _parse_tool_call_args(tc)
            lines.append(_render_tool_call_line(name, args))
            tid = tc.get("id") or ""
            result_msg = tid_to_result.get(tid)
            if result_msg is not None:
                text = normalize_content(result_msg.get("content", "")).strip()
                if text:
                    lines.append(text)
        return _render_tool_history_block("\n".join(lines))

    def supports_streaming(self) -> bool:
        return True
