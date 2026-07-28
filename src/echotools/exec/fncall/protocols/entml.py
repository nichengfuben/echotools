"""Entropy ML (entml) 协议实现。

- 工具调用：<entml:invoke> / <entml:parameter>（legacy ``function_calls`` 外壳仅解析兼容）
- 对话历史：<entml:conversation_history>
- 当前用户消息：<current_user_message>
"""

from __future__ import annotations

import json as _json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_TOOL_INVOKE_REMINDER_EN,
)
from echotools.exec.fncall.protocols.entml_invoke import (
    parse_entml_tool_calls,
)
from echotools.exec.fncall.protocols.entml_patterns import (
    BLOCK_RE,
    entml_invoke_open_may_be_streaming,
    extract_attr_value,
    normalize_entml_name,
    strip_legacy_function_calls_wrapper,
    strip_tool_entml_residue,
)
from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_section,
)
from echotools.exec.fncall.protocols.entml_tools import format_entml_tool_descs
from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.normalization import (
    normalize_content,
    normalize_tool_calls,
)
from echotools.exec.protocol.base import ToolProtocol

# 仅按 entml: 前缀剥离标签，不区分具体标签名。
_ENTML_PAIR_RE = re.compile(
    r"<entml:[a-zA-Z_][\w]*\b[^>]*>.*?</entml:[a-zA-Z_][\w]*>",
    re.DOTALL,
)
_ENTML_SELF_CLOSING_RE = re.compile(r"<entml:[a-zA-Z_][\w]*\b[^>]*/>", re.DOTALL)
_ENTML_ORPHAN_CLOSE_RE = re.compile(r"</entml:[a-zA-Z_][\w]*>", re.DOTALL)
_ENTML_ORPHAN_OPEN_RE = re.compile(r"<entml:[a-zA-Z_][\w]*\b[^>]*>", re.DOTALL)


def strip_entml_from_content(content: str) -> str:
    """从 user 消息正文剥离所有 entml:* 标签及残留开闭标签。"""
    if not content:
        return content
    cleaned = content
    cleaned = _ENTML_PAIR_RE.sub("", cleaned)
    cleaned = _ENTML_SELF_CLOSING_RE.sub("", cleaned)
    cleaned = _ENTML_ORPHAN_CLOSE_RE.sub("", cleaned)
    cleaned = _ENTML_ORPHAN_OPEN_RE.sub("", cleaned)
    return cleaned.strip()


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


def _is_simple_scalar(value: Any) -> bool:
    """单行、无引号/括号/尖括号的短字符串，可省略 JSON 对象外壳。"""
    if not isinstance(value, str):
        return False
    if not value or "\n" in value or "\r" in value:
        return False
    if any(ch in value for ch in ('"', "{", "}", "[", "]", "<", ">")):
        return False
    return True


def _render_tool_call_line(name: str, args: Dict[str, Any]) -> str:
    """History 内已完成工具调用：{ToolName: json}；单简单标量可写 {ToolName: value}。"""
    if len(args) == 1:
        val = next(iter(args.values()))
        if _is_simple_scalar(val):
            return f"{{{name}: {val}}}"
    return f"{{{name}: {_json.dumps(args, ensure_ascii=False)}}}"


def _render_tool_history_block(body: str) -> str:
    """将工具轮次正文包裹为 <tool> 块。"""
    return f"<tool>\n{body.strip()}\n</tool>"


_ENTML_INSTRUCTION = """\
In this environment you have access to a set of tools you can use to answer the user's question.
You can invoke functions by writing a "<entml:invoke>" block like the following as part of your reply to the user:

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
    _LEGACY_WRAPPER_PREFIX = "<entml:function_calls"
    _THINKING_PREFIX = "<entml:thinking"

    def get_trigger_tags(self) -> List[str]:
        # invoke / thinking 前缀 holdback，避免 `<e` 歧义被提前吐出
        return [
            self._TRIGGER,
            self._TRIGGER_PREFIX,
            self._THINKING_PREFIX,
            f"{self._THINKING_PREFIX}>",
        ]

    def normalize_stream_buffer(self, buffer: str) -> str:
        """流式处理前剥离 legacy function_calls 外壳（提示词已不再要求）。"""
        return strip_legacy_function_calls_wrapper(buffer)

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
        history_markup_warning: str = "",
        current_user_message: Optional[str] = None,
        protocol_options: Optional[Dict[str, Any]] = None,
        history_has_tool_calls: bool = False,
    ) -> str:
        if tool_descs:
            sections: List[str] = [
                _ENTML_INSTRUCTION.rstrip() + "\n\n" + tool_descs
            ]
        else:
            sections = [_ENTML_INSTRUCTION.rstrip()]

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

        if history_markup_warning:
            sections.append(
                f"<history_markup_warning>\n{history_markup_warning}\n</history_markup_warning>"
            )

        if current_user_message is not None:
            sections.append(format_entml_current_user_message(current_user_message))

        # thinking 放在最后，超限截断时优先保留在 send_text 尾部
        thinking_section = build_entml_thinking_section(
            protocol_options, has_tools=bool(tool_descs)
        )
        if thinking_section:
            sections.append(thinking_section)

        return "\n\n".join(sections)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        """invoke 开标签（含 name 且闭合 ``>``）稳定后才视为工具流开始。"""
        invoke_pos = self._find_complete_invoke_open(buffer)
        if invoke_pos < 0:
            return (False, -1)
        return (True, invoke_pos)

    def find_fncall_hold_from(self, buffer: str) -> Optional[int]:
        """invoke 未稳定前 hold 前缀；legacy 外壳开标签未闭合时同样 hold。"""
        if self._find_complete_invoke_open(buffer) >= 0:
            return None
        hold: Optional[int] = None
        legacy_pos = buffer.find(self._LEGACY_WRAPPER_PREFIX)
        if legacy_pos >= 0:
            close = buffer.find(">", legacy_pos)
            if close < 0 and (hold is None or legacy_pos < hold):
                hold = legacy_pos
        invoke_pos = buffer.find(self._TRIGGER_PREFIX)
        if (
            invoke_pos >= 0
            and entml_invoke_open_may_be_streaming(buffer, invoke_pos)
            and (hold is None or invoke_pos < hold)
        ):
            hold = invoke_pos
        return hold

    def _find_complete_invoke_open(self, buffer: str) -> int:
        """返回首个含 name 且已闭合 ``>`` 的 ``<entml:invoke`` 起始下标；否则 -1。"""
        search_from = 0
        prefix_len = len(self._TRIGGER_PREFIX)
        while True:
            pos = buffer.find(self._TRIGGER_PREFIX, search_from)
            if pos < 0:
                return -1
            close = buffer.find(">", pos + prefix_len)
            if close < 0:
                return -1
            attrs = buffer[pos + prefix_len : close]
            name = extract_attr_value(attrs, "name")
            if name and normalize_entml_name(name):
                return pos
            search_from = close + 1

    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
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
        parse_text, _ = strip_fake_history_markup(parse_text)
        tool_calls = parse_entml_tool_calls(parse_text, tools, schema_index)
        clean = text[:unclosed_open_at] if unclosed_open_at >= 0 else text
        if tool_calls:
            clean = BLOCK_RE.sub("", clean)
        # 无论是否解析成功，都剥离工具相关残留，避免标签泄露；thinking 保留给后续 split。
        clean = strip_tool_entml_residue(clean)
        clean, _ = strip_fake_history_markup(clean)
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

    def clean_tool_tags(self, content: str) -> str:
        """仅剥离工具相关标签残留，保留 thinking；并移除伪 history 块。"""
        cleaned = strip_tool_entml_residue(content)
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
