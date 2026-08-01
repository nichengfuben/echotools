"""Entropy ML (entml) 协议实现。

- 工具调用：<entml:invoke> / <entml:parameter>
- 对话历史：<entml:conversation_history>
- 当前用户消息：<current_user_message>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_may_be_streaming,
    find_actionable_entml_invoke_open,
    resolve_known_tool_names,
    strip_actionable_entml_invoke_blocks,
    strip_tool_entml_residue,
)
from echotools.exec.fncall.protocols.entml_schema import format_entml_tool_descs
from echotools.exec.fncall.protocols.entml_tool.fakemarkup import (
    strip_orphan_entml_close_tags,
)
from echotools.exec.fncall.protocols.entml_tool.invoke import (
    format_entml_tool_calls,
    parse_entml_tool_calls,
)
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.entml_format import (
    _parse_tool_call_args,
    _render_tool_call_line,
    build_entml_render_prompt,
    format_entml_conversation_history,
    format_entml_current_user_message,
    format_entml_functions_results,
    format_tool_result_id_comment,
    strip_entml_from_content,
)
from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup
from echotools.exec.fncall.shared.normalization import normalize_tool_calls
from echotools.exec.protocol.base import ToolProtocol

__all__ = [
    "EntmlProtocol",
    "format_entml_conversation_history",
    "format_entml_current_user_message",
    "format_entml_functions_results",
    "format_tool_result_id_comment",
    "strip_entml_from_content",
]


class EntmlProtocol(ToolProtocol):
    """Entropy ML (entml) 格式工具调用协议适配器。"""

    @property
    def id(self) -> str:
        return "entml"

    _TRIGGER = "<entml:invoke>"
    _TRIGGER_PREFIX = "<entml:invoke"
    _THINKING_PREFIX = "<entml:thinking"

    def get_trigger_tags(self) -> List[str]:
        return [
            self._TRIGGER,
            self._TRIGGER_PREFIX,
            self._THINKING_PREFIX,
            f"{self._THINKING_PREFIX}>",
        ]

    def normalize_stream_buffer(self, buffer: str) -> str:
        return buffer

    def get_stream_end_tags(self) -> List[str]:
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
        history_markup_warning: str = "",
        current_user_message: Optional[str] = None,
        protocol_options: Optional[Dict[str, Any]] = None,
        history_has_tool_calls: bool = False,
        functions_results_text: str = "",
    ) -> str:
        _ = (lang, history_has_tool_calls)
        return build_entml_render_prompt(
            tool_descs=tool_descs,
            user_system_prompt=user_system_prompt,
            history_text=history_text,
            loop_warning=loop_warning,
            history_markup_warning=history_markup_warning,
            current_user_message=current_user_message,
            protocol_options=protocol_options,
            functions_results_text=functions_results_text,
        )

    def detect_start(
        self,
        buffer: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, int]:
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        invoke_pos = find_actionable_entml_invoke_open(buffer, known_names=known)
        if invoke_pos < 0:
            return (False, -1)
        return (True, invoke_pos)

    def find_fncall_hold_from(
        self,
        buffer: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[int]:
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        if find_actionable_entml_invoke_open(buffer, known_names=known) >= 0:
            return None
        hold: Optional[int] = None
        invoke_pos = buffer.find(self._TRIGGER_PREFIX)
        if (
            invoke_pos >= 0
            and entml_invoke_open_may_be_streaming(
                buffer, invoke_pos, known_names=known
            )
            and (hold is None or invoke_pos < hold)
        ):
            hold = invoke_pos
        return hold

    def _find_complete_invoke_open(
        self,
        buffer: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        return find_actionable_entml_invoke_open(buffer, known_names=known)

    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        include_tool_blocks: bool = True,
        thinking_enabled: bool = True,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        _ = include_tool_blocks
        from echotools.exec.fncall.protocols.entml_think.parse import (
            _find_earliest_thinking_open,
            has_unclosed_entml_thinking,
            split_entml_thinking,
        )

        schema_index = _build_param_schema_index(tools) if tools else None
        parse_text, _thinking = split_entml_thinking(text, thinking_enabled=True)
        unclosed_open_at = -1
        if has_unclosed_entml_thinking(text, thinking_enabled=True):
            unclosed_open_at, _ = _find_earliest_thinking_open(
                text, thinking_enabled=True
            )
            if unclosed_open_at >= 0:
                parse_text = text[:unclosed_open_at]
        known = resolve_known_tool_names(tools, schema_index)
        tool_calls = parse_entml_tool_calls(parse_text, tools, schema_index)
        clean = text[:unclosed_open_at] if unclosed_open_at >= 0 else text
        if thinking_enabled:
            visible, _ = split_entml_thinking(clean, thinking_enabled=True)
            clean = visible
        clean, _ = strip_fake_history_markup(clean)
        if tool_calls:
            clean = strip_actionable_entml_invoke_blocks(clean, known_names=known)
        clean = strip_tool_entml_residue(clean, known_names=known)
        clean, _ = strip_orphan_entml_close_tags(clean)
        return (clean, normalize_tool_calls(tool_calls, tools))

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content: str) -> str:
        return strip_entml_from_content(content)

    def clean_tool_tags(
        self,
        content: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        cleaned = strip_tool_entml_residue(content, known_names=known)
        cleaned, _ = strip_fake_history_markup(cleaned)
        return cleaned

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
        _ = tid_to_result
        lines: List[str] = []
        for tc in tool_calls:
            invoke = format_entml_tool_calls([tc])
            if invoke:
                lines.append(invoke)
            tid = tc.get("id") or ""
            comment = format_tool_result_id_comment(tid)
            if comment:
                lines.append(comment)
        return "\n".join(lines)

    def supports_streaming(self) -> bool:
        return True
