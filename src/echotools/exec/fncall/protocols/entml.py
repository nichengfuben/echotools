"""Entropy ML (entml) 协议实现。

- 工具调用：<entml:invoke> / <entml:parameter>（legacy ``function_calls`` 外壳仅解析兼容）
- 对话历史：<entml:conversation_history>
- 当前用户消息：<current_user_message>
"""

from __future__ import annotations

import json as _json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.behavior_blocks import (
    format_function_calling_behavior,
    format_hard_constraint_restatement,
    format_thinking_behavior,
)
from echotools.exec.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
)
from echotools.exec.fncall.protocols.entml_invoke import (
    format_entml_tool_calls,
    parse_entml_tool_calls,
)
from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_may_be_streaming,
    extract_attr_value,
    find_actionable_entml_invoke_open,
    normalize_entml_name,
    resolve_known_tool_names,
    strip_actionable_entml_invoke_blocks,
    strip_legacy_function_calls_wrapper,
    strip_tool_entml_residue,
)
from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_behavior_section,
    build_entml_thinking_meta_section,
)
from echotools.exec.fncall.protocols.entml_schema import format_entml_tool_descs
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup
from echotools.exec.fncall.shared.normalization import (
    normalize_content,
    normalize_tool_calls,
)
from echotools.exec.protocol.base import ToolProtocol

# user 消息：仅去掉标签名中的 entml: 命名空间，保留标签与正文。
_ENTML_NAMESPACE_RE = re.compile(r"(</?)entml:", re.IGNORECASE)


def strip_entml_from_content(content: str) -> str:
    """user 消息：去掉 ``entml:`` 标签前缀，保留标签结构与正文（含 ``//``）。"""
    if not content:
        return content
    return _ENTML_NAMESPACE_RE.sub(r"\1", content)


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
    """历史内联工具轮次正文（invoke + result，无 ``<tool>`` 外壳）。"""
    return body.strip()


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

Your turn ends immediately at the closing tag of the last <entml:invoke> block you emit. You append nothing after it — no comment, no result, no id, no visible text. The execution environment then runs each tool. Once a turn is complete, the environment logs it into <entml:conversation_history> and appends, after each invocation in that log, an HTML comment stating the environment-generated result id in the form <!-- Tool Result ID:{id} -->. This comment is written by the environment when logging a completed turn; you never write it yourself, in this turn or in imitation of any prior turn, because at the moment you emit an invocation the id does not yet exist. Separately, the environment appends the full content of every result, matched by id, to a single flat top-level block named <entml:funtions_results>, positioned outside and independent of <entml:conversation_history>. This block accumulates across the whole conversation; it is never nested inside conversation_history and never adjacent to an invocation.

Here are the functions available in JSONSchema format:
"""


def format_tool_result_id_comment(tool_call_id: str) -> str:
    """History 内 invoke 后的环境回填 id 注释（非模型实时输出）。"""
    tid = (tool_call_id or "").strip()
    if not tid:
        return ""
    return f"<!-- Tool Result ID:{tid} -->"


def format_entml_functions_results(
    entries: List[Tuple[str, str]],
) -> str:
    """顶层 ``<entml:funtions_results>``：整场对话累计的 result 条目。"""
    if not entries:
        return ""
    lines: List[str] = []
    for tid, text in entries:
        tid = (tid or "").strip()
        body = (text or "").strip()
        if not tid or not body:
            continue
        lines.append(f'<entml:result id="{tid}">\n{body}\n</entml:result>')
    if not lines:
        return ""
    return (
        f"<entml:funtions_results>\n"
        + "\n".join(lines)
        + "\n</entml:funtions_results>"
    )


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
        # invoke / thinking / 伪 history tool 前缀 holdback，避免 `<e` / `<t` 歧义被提前吐出
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
        functions_results_text: str = "",
    ) -> str:
        _ = history_has_tool_calls
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

        if loop_warning:
            sections.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")

        if history_markup_warning:
            sections.append(
                f"<history_markup_warning>\n{history_markup_warning}\n</history_markup_warning>"
            )

        if history_text:
            sections.append(
                format_entml_conversation_history(history_text, _HISTORY_CLARIFY_EN)
            )

        if functions_results_text.strip():
            sections.append(functions_results_text.strip())

        if tool_descs:
            sections.append(format_function_calling_behavior())

        thinking_behavior = build_entml_thinking_behavior_section(
            protocol_options, history_text=history_text
        )
        if thinking_behavior:
            sections.append(thinking_behavior)

        if tool_descs:
            sections.append(format_hard_constraint_restatement())

        if current_user_message is not None:
            sections.append(format_entml_current_user_message(current_user_message))

        thinking_meta = build_entml_thinking_meta_section(protocol_options)
        if thinking_meta:
            sections.append(thinking_meta)

        return "\n\n".join(sections)

    def detect_start(
        self,
        buffer: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, int]:
        """invoke 开标签（闭合 ``>`` 且 name 在 tools 内）稳定后才视为工具流开始。"""
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
        """invoke 未稳定前 hold 前缀；legacy 外壳开标签未闭合时同样 hold。"""
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        if find_actionable_entml_invoke_open(buffer, known_names=known) >= 0:
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
        """返回首个可解析 ``<entml:invoke`` 起始下标；否则 ``-1``。"""
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
        # 工具解析始终按 thinking 开启语义分流（fault ``</thinking>`` 等）；可见正文再按 thinking_enabled 剥离。
        parse_text, _thinking = split_entml_thinking(text, thinking_enabled=True)
        unclosed_open_at = -1
        if has_unclosed_entml_thinking(text, thinking_enabled=True):
            unclosed_open_at, _ = _find_earliest_thinking_open(
                text, thinking_enabled=True
            )
            if unclosed_open_at >= 0:
                parse_text = text[:unclosed_open_at]
        schema_index = _build_param_schema_index(tools) if tools else None
        known = resolve_known_tool_names(tools, schema_index)
        tool_calls = parse_entml_tool_calls(parse_text, tools, schema_index)
        clean = text[:unclosed_open_at] if unclosed_open_at >= 0 else text
        if thinking_enabled:
            # fault ``</thinking>`` 须借后续 invoke 判定闭合；thinking 剥离必须在 invoke 移除之前。
            visible, _ = split_entml_thinking(clean, thinking_enabled=True)
            clean = visible
        clean, _ = strip_fake_history_markup(clean)
        if tool_calls:
            clean = strip_actionable_entml_invoke_blocks(clean, known_names=known)
        clean = strip_tool_entml_residue(clean, known_names=known)
        from echotools.exec.fncall.protocols.entml_fake_structure_markup import (
            strip_orphan_entml_close_tags,
        )

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
        """user 消息：仅去掉 ``entml:`` 前缀，不做其它剥离。"""
        return strip_entml_from_content(content)

    def clean_tool_tags(
        self,
        content: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """仅剥离工具相关标签残留，保留 thinking；并移除伪 history 块。"""
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
        """同一 assistant 轮次：``<entml:invoke>`` + 环境回填 id 注释（无 result 正文）。"""
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
