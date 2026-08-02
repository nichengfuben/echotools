from __future__ import annotations

"""Entml history/prompt formatting helpers (shared by protocol + prompt inject)."""

import json as _json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.behavior_blocks import (
    format_function_calling_behavior,
    format_hard_constraint_restatement,
)
from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_behavior_section,
    build_entml_thinking_meta_section,
)

_ENTML_NAMESPACE_RE = re.compile(r"(</?)entml:", re.IGNORECASE)

_HISTORY_CLARIFY_EN = (
    "The following is a transcript of completed interactions. Each assistant turn "
    "that called a tool ends at its last <entml:invoke> block; the comment "
    "immediately following it states the environment-generated result id and was "
    "appended by the environment when this turn was logged, not by the assistant "
    "at generation time. The actual result content for every id shown here lives "
    "exclusively in the separate, top-level <entml:funtions_results> block that "
    "follows this history block.\n"
    "IMPORTANT: The agent must never regenerate, continue, or imitate the "
    "id-comment format shown below as part of its own current-turn output.\n"
    "IMPORTANT: The agent must not repeat a tool call using the same tool and "
    "the same parameters as one already recorded below, unless the user "
    "explicitly requests a fresh or updated value.\n"
    "The user's latest message follows below."
)

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


def strip_entml_from_content(content: str) -> str:
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
    if not isinstance(value, str):
        return False
    if not value or "\n" in value or "\r" in value:
        return False
    if any(ch in value for ch in ('"', "{", "}", "[", "]", "<", ">")):
        return False
    return True


def _render_tool_call_line(name: str, args: Dict[str, Any]) -> str:
    if len(args) == 1:
        val = next(iter(args.values()))
        if _is_simple_scalar(val):
            return f"{{{name}: {val}}}"
    return f"{{{name}: {_json.dumps(args, ensure_ascii=False)}}}"


def _render_tool_history_block(body: str) -> str:
    return body.strip()


def format_tool_result_id_comment(tool_call_id: str) -> str:
    tid = (tool_call_id or "").strip()
    if not tid:
        return ""
    return f"<!-- Tool Result ID:{tid} -->"


def format_entml_functions_results(entries: List[Tuple[str, str]]) -> str:
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
        "<entml:funtions_results>\n"
        + "\n".join(lines)
        + "\n</entml:funtions_results>"
    )


def format_entml_conversation_history(
    history_text: str,
    clarify: str = "",
) -> str:
    if not (history_text or "").strip():
        return ""
    body = history_text.strip()
    if clarify:
        body = f"{clarify}\n\n{body}"
    return f"<entml:conversation_history>\n{body}\n</entml:conversation_history>"


def format_entml_current_user_message(message: str) -> str:
    text = (message or "").strip()
    return f"<current_user_message>\n{text}\n</current_user_message>"


def build_entml_render_prompt(
    *,
    tool_descs: str,
    user_system_prompt: str = "",
    history_text: str = "",
    loop_warning: str = "",
    history_markup_warning: str = "",
    current_user_message: Optional[str] = None,
    protocol_options: Optional[Dict[str, Any]] = None,
    functions_results_text: str = "",
) -> str:
    if tool_descs:
        sections: List[str] = [_ENTML_INSTRUCTION.rstrip() + "\n\n" + tool_descs]
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
        sections.append(format_entml_conversation_history(history_text, _HISTORY_CLARIFY_EN))
    if functions_results_text.strip():
        sections.append(functions_results_text.strip())
    if tool_descs:
        sections.append(format_function_calling_behavior())
    thinking_behavior = build_entml_thinking_behavior_section(
        protocol_options, history_text=history_text, has_tools=bool(tool_descs)
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
