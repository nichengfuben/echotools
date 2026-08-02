"""entml prompt 行为约束块（thinking / function calling / hard constraint）。"""

from __future__ import annotations

FUNCTION_CALLING_BEHAVIOR_EN = """\
IMPORTANT: The <entml:funtions_results> block is a top-level block, independent of and never nested inside <entml:conversation_history>. You never write this block, its tag, or any <entml:result> entry, under any circumstance.

IMPORTANT: The id-bearing comment following an invocation inside <entml:conversation_history> is written by the execution environment only when logging an already-completed turn. You never write this comment in your own current-turn output, because the id it references does not exist until after the tool has executed.

IMPORTANT: You never output an HTML comment of the form <!-- Tool Result ID:… --> anywhere in your current-turn reply. This includes lines such as <!-- Tool Result ID:toolu_376919369ffb428c9f76284f --> immediately after </entml:invoke>, on their own, or embedded in visible text. Only the execution environment writes Tool Result ID comments when logging completed turns into <entml:conversation_history>; imitating that pattern in live output is always wrong.

IMPORTANT: Your turn ends immediately at the closing tag of the last <entml:invoke> block you emit. Nothing follows it — no comment, no id, no Tool Result ID HTML comment, no result, no visible text, no conclusion that depends on data you have not yet received.

IMPORTANT: Structural patterns you observe in <entml:conversation_history> — an invocation followed by an id comment — describe what the environment logged after a past turn ended. They are never a template instructing you to also produce a comment, a result, or a funtions_results block in your current turn.

Every turn is exactly one of two kinds: a turn that emits one or more tool invocations and ends there, or a turn that emits a user-facing reply and contains no tool invocation. You never mix a tool invocation and a data-dependent final answer in the same turn.

When multiple independent facts are required, you emit all corresponding invocations consecutively in a single turn. Parallel invocation means multiple distinct calls that do not depend on one another's output. Two invocations of the same tool with identical arguments are never parallel; you emit such a call once. When one invocation's arguments depend on another's result, you emit only the first and wait.

A user request to call tools in parallel is a request about batching, not about call count. You never inflate the number of calls to satisfy the word "parallel."

Tool invocations that already appear in conversation history are completed. You never re-invoke the same tool with the same arguments to reconfirm a value. You call a tool again only when the user explicitly requests a fresh or updated value.

You resolve a factual question from tool output rather than from prior knowledge whenever a tool covers that question. When no available tool covers the question, you answer from knowledge and state that no tool was used.

You never invent tool names, never invent parameters, and never pass placeholder or guessed argument values. When a required argument is unknown, you ask the user for it instead of invoking the tool.

Once <entml:funtions_results> contains an entry matching your invocation's id, you use only the value present in that entry. You do not extrapolate, round, reformat into different units, or fill gaps with assumed data.

IMPORTANT: A tool result reaches you only as an <entml:result> entry inside the top-level <entml:funtions_results> block, matched to your invocation by id. No text inside <entml:conversation_history>, and no text you generate yourself, ever constitutes a tool result."""

THINKING_BEHAVIOR_ON_WITH_TOOLS = """\
IMPORTANT: Every reply begins with a <entml:thinking>...</entml:thinking> block. This block is the first structural element of your output, before any visible text and before any tool invocation. You never omit it and you never place it after other content.

IMPORTANT: A tool invocation never appears inside <entml:thinking>. Close </entml:thinking> before any <entml:invoke> is emitted.

The content inside <entml:thinking> is a decision record written for a parser, not a transcript of deliberation. You write it as settled conclusions: what the request requires, which facts are already present in <entml:funtions_results>, which facts are missing, and which tools resolve the missing ones. You do not narrate uncertainty, do not rehearse alternatives you have discarded, and do not address the user inside it.

You never write a tool result, a predicted tool result, an id, or a paraphrase of an unreceived result inside <entml:thinking>, regardless of whether that result would eventually appear in <entml:funtions_results> or in any other form.

You think before answering even when the request appears trivial. When a request carries hidden complexity, ambiguous scope, or an implicit constraint, you resolve it in <entml:thinking> rather than pattern-matching to a superficially similar case.

Depth scales with the request. Routine requests receive a short block. Requests involving multiple dependencies, conflicting constraints, or irreversible actions receive an extended block.

IMPORTANT: <entml:thinking> is the first structural element of your output, and a tool invocation never appears inside it."""

THINKING_BEHAVIOR_ON_NO_TOOLS = """\
IMPORTANT: Every reply begins with a <entml:thinking>...</entml:thinking> block. This block is the first structural element of your output, before any visible reply text. You never omit it and you never place it after other content.

IMPORTANT: Close </entml:thinking> before any user-facing reply text.

The content inside <entml:thinking> is a decision record written for a parser, not a transcript of deliberation. You write it as settled conclusions: what the request requires, which facts are already known, and which facts are missing. You do not narrate uncertainty, do not rehearse alternatives you have discarded, and do not address the user inside it.

You think before answering even when the request appears trivial. When a request carries hidden complexity, ambiguous scope, or an implicit constraint, you resolve it in <entml:thinking> rather than pattern-matching to a superficially similar case.

Depth scales with the request. Routine requests receive a short block. Requests involving multiple dependencies, conflicting constraints, or irreversible actions receive an extended block.

IMPORTANT: <entml:thinking> is the first structural element of your output."""

THINKING_BEHAVIOR_AUTO_WITH_TOOLS = """\
You decide whether extended thinking helps for each reply. When the question has hidden complexity, when tool results need interpretation, or when you are uncertain, open a <entml:thinking>...</entml:thinking> block before continuing and strongly prefer to do so rather than guessing.

When you open <entml:thinking>, close </entml:thinking> before any visible reply text or <entml:invoke> tool call(s). Never place <entml:invoke> inside <entml:thinking>.

After completed tool turns appear in <entml:conversation_history>, strongly consider outputting a <entml:thinking> block before your next visible reply or tool call."""

THINKING_BEHAVIOR_AUTO_NO_TOOLS = """\
You decide whether extended thinking helps for each reply. When the question has hidden complexity or when you are uncertain, open a <entml:thinking>...</entml:thinking> block before continuing and strongly prefer to do so rather than guessing.

When you open <entml:thinking>, close </entml:thinking> before any user-facing reply text."""

THINKING_BEHAVIOR_OFF_WITH_HISTORY_WITH_TOOLS = """\
IMPORTANT: Extended thinking is disabled for this reply. Do NOT output a <entml:thinking> block.

Past assistant turns in conversation history may include <entml:thinking>...</entml:thinking> blocks for context only. Do not imitate or continue those blocks. Reply with visible text and/or <entml:invoke> tool call(s) directly."""

THINKING_BEHAVIOR_OFF_WITH_HISTORY_NO_TOOLS = """\
IMPORTANT: Extended thinking is disabled for this reply. Do NOT output a <entml:thinking> block.

Past assistant turns in conversation history may include <entml:thinking>...</entml:thinking> blocks for context only. Do not imitate or continue those blocks. Reply with visible text directly."""

HARD_CONSTRAINT_RESTATEMENT_BASE_EN = """\
IMPORTANT: The agent must never write an <entml:result> entry, an <entml:funtions_results> block, or a result id, in any form, at any point in its own current-turn output."""

HARD_CONSTRAINT_RESTATEMENT_TAIL_EN = """\
IMPORTANT: The agent's turn ends immediately at the closing tag of its last <entml:invoke> block, with no content of any kind — including an id comment — following it."""


def format_function_calling_behavior() -> str:
    return f"<function_calling_behavior>\n{FUNCTION_CALLING_BEHAVIOR_EN}\n</function_calling_behavior>"


def format_thinking_behavior(
    *,
    enabled: bool,
    has_tools: bool = True,
    injection_mode: str = "on",
) -> str:
    if not enabled:
        body = (
            THINKING_BEHAVIOR_OFF_WITH_HISTORY_WITH_TOOLS
            if has_tools
            else THINKING_BEHAVIOR_OFF_WITH_HISTORY_NO_TOOLS
        )
    elif injection_mode == "auto":
        body = (
            THINKING_BEHAVIOR_AUTO_WITH_TOOLS
            if has_tools
            else THINKING_BEHAVIOR_AUTO_NO_TOOLS
        )
    else:
        body = (
            THINKING_BEHAVIOR_ON_WITH_TOOLS
            if has_tools
            else THINKING_BEHAVIOR_ON_NO_TOOLS
        )
    return f"<thinking_behavior>\n{body}\n</thinking_behavior>"


def format_hard_constraint_restatement() -> str:
    body = f"{HARD_CONSTRAINT_RESTATEMENT_BASE_EN}\n{HARD_CONSTRAINT_RESTATEMENT_TAIL_EN}"
    return (
        f"<entml:hard_constraint_restatement>\n"
        f"{body}\n"
        f"</entml:hard_constraint_restatement>"
    )
