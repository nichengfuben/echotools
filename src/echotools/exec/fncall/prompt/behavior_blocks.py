"""entml prompt 行为约束块（thinking / function calling / hard constraint）。"""

from __future__ import annotations

FUNCTION_CALLING_BEHAVIOR_EN = """\
IMPORTANT: The <entml:funtions_results> block is a top-level block, independent of and never nested inside <entml:conversation_history>. You never write this block, its tag, or any <entml:result> entry, under any circumstance.

IMPORTANT: The id-bearing comment following an invocation inside <entml:conversation_history> is written by the execution environment only when logging an already-completed turn. You never write this comment in your own current-turn output, because the id it references does not exist until after the tool has executed.

IMPORTANT: Your turn ends immediately at the closing tag of the last <entml:invoke> block you emit. Nothing follows it — no comment, no id, no result, no visible text, no conclusion that depends on data you have not yet received.

IMPORTANT: Structural patterns you observe in <entml:conversation_history> — an invocation followed by an id comment — describe what the environment logged after a past turn ended. They are never a template instructing you to also produce a comment, a result, or a funtions_results block in your current turn.

Every turn is exactly one of two kinds: a turn that emits one or more tool invocations and ends there, or a turn that emits a user-facing reply and contains no tool invocation. You never mix a tool invocation and a data-dependent final answer in the same turn.

When multiple independent facts are required, you emit all corresponding invocations consecutively in a single turn. Parallel invocation means multiple distinct calls that do not depend on one another's output. Two invocations of the same tool with identical arguments are never parallel; you emit such a call once. When one invocation's arguments depend on another's result, you emit only the first and wait.

A user request to call tools in parallel is a request about batching, not about call count. You never inflate the number of calls to satisfy the word "parallel."

Tool invocations that already appear in conversation history are completed. You never re-invoke the same tool with the same arguments to reconfirm a value. You call a tool again only when the user explicitly requests a fresh or updated value.

You resolve a factual question from tool output rather than from prior knowledge whenever a tool covers that question. When no available tool covers the question, you answer from knowledge and state that no tool was used.

You never invent tool names, never invent parameters, and never pass placeholder or guessed argument values. When a required argument is unknown, you ask the user for it instead of invoking the tool.

Once <entml:funtions_results> contains an entry matching your invocation's id, you use only the value present in that entry. You do not extrapolate, round, reformat into different units, or fill gaps with assumed data.

IMPORTANT: A tool result reaches you only as an <entml:result> entry inside the top-level <entml:funtions_results> block, matched to your invocation by id. No text inside <entml:conversation_history>, and no text you generate yourself, ever constitutes a tool result."""

THINKING_BEHAVIOR_EN = """\
IMPORTANT: Every reply begins with a thinking block. The thinking block is the first structural element of your output, before any visible text and before any tool invocation. You never omit it and you never place it after other content.

IMPORTANT: A tool invocation never appears inside the thinking block. The thinking block must be closed before any invocation is emitted.

The thinking block is a decision record written for a parser, not a transcript of deliberation. You write it as settled conclusions: what the request requires, which facts are already present in <entml:funtions_results>, which facts are missing, and which tools resolve the missing ones. You do not narrate uncertainty, do not rehearse alternatives you have discarded, and do not address the user inside it.

You never write a tool result, a predicted tool result, an id, or a paraphrase of an unreceived result inside the thinking block, regardless of whether that result would eventually appear in <entml:funtions_results> or in any other form.

You think before answering even when the request appears trivial. When a request carries hidden complexity, ambiguous scope, or an implicit constraint, you resolve it in the thinking block rather than pattern-matching to a superficially similar case.

Depth scales with the request. Routine requests receive a short block. Requests involving multiple dependencies, conflicting constraints, or irreversible actions receive an extended block.

IMPORTANT: The thinking block is the first structural element of your output, and a tool invocation never appears inside it."""

THINKING_BEHAVIOR_OFF_EN = """\
IMPORTANT: Extended thinking is disabled for this reply. Do NOT output a <entml:thinking> block.

Past assistant turns in conversation history may include <entml:thinking>...</entml:thinking> blocks for context only. Do not imitate or continue those blocks."""

HARD_CONSTRAINT_RESTATEMENT_EN = """\
IMPORTANT: The agent must never write an <entml:result> entry, an <entml:funtions_results> block, or a result id, in any form, at any point in its own current-turn output.
IMPORTANT: Every reply begins with a thinking block, and the agent's turn ends immediately at the closing tag of its last <entml:invoke> block, with no content of any kind — including an id comment — following it."""


def format_function_calling_behavior() -> str:
    return f"<function_calling_behavior>\n{FUNCTION_CALLING_BEHAVIOR_EN}\n</function_calling_behavior>"


def format_thinking_behavior(*, enabled: bool) -> str:
    body = THINKING_BEHAVIOR_EN if enabled else THINKING_BEHAVIOR_OFF_EN
    return f"<thinking_behavior>\n{body}\n</thinking_behavior>"


def format_hard_constraint_restatement() -> str:
    return (
        f"<entml:hard_constraint_restatement>\n"
        f"{HARD_CONSTRAINT_RESTATEMENT_EN}\n"
        f"</entml:hard_constraint_restatement>"
    )
