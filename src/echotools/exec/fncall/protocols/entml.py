"""Entropy ML (entml) 协议实现。

- 工具调用：<entml:function_calls> / <entml:invoke> / <entml:parameter>
- 对话历史：<entml:conversation_history>
- 当前用户消息：<entml:current_user_message>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.templates import _HISTORY_CLARIFY_EN
from echotools.exec.fncall.protocols.entml_invoke import (
    format_entml_tool_calls,
    parse_entml_tool_calls,
)
from echotools.exec.fncall.protocols.entml_patterns import BLOCK_RE
from echotools.exec.fncall.protocols.entml_thinking import build_entml_thinking_section
from echotools.exec.fncall.protocols.entml_tools import format_entml_tool_descs
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.normalization import normalize_tool_calls
from echotools.exec.protocol.base import ToolProtocol

_ENTML_INSTRUCTION = """\
In this environment you have access to a set of tools you can use to answer the user's question.
You can invoke functions by writing a "<entml:function_calls>" block like the following as part of your reply to the user:

<entml:function_calls>
<entml:invoke name="$FUNCTION_NAME">
<entml:parameter name="$PARAMETER_NAME">$PARAMETER_VALUE</entml:parameter>
...
</entml:invoke>
<entml:invoke name="$FUNCTION_NAME2">
...
</entml:invoke>
</entml:function_calls>

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
    """将当前用户消息包裹为 <entml:current_user_message> 块。"""
    text = (message or "").strip()
    return f"<entml:current_user_message>\n{text}\n</entml:current_user_message>"


class EntmlProtocol(ToolProtocol):
    """Entropy ML (entml) 格式工具调用协议适配器。"""

    @property
    def id(self) -> str:
        return "entml"

    _TRIGGER = "<entml:function_calls>"
    _TRIGGER_PREFIX = "<entml:function_calls"

    def get_trigger_tags(self) -> List[str]:
        return [self._TRIGGER]

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
    ) -> str:
        sections: List[str] = [_ENTML_INSTRUCTION + tool_descs]

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

        if loop_warning:
            sections.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")

        sections.append(format_entml_current_user_message(current_user_message))
        return "\n\n".join(sections)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        pos = buffer.find(self._TRIGGER_PREFIX)
        if pos < 0:
            return (False, -1)
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
        return format_entml_tool_calls(tool_calls)

    def supports_streaming(self) -> bool:
        return True
