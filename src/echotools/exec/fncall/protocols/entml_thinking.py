from __future__ import annotations

from typing import Any, Dict, Optional

_CANONICAL_MODES = frozenset({"off", "on", "auto", "interleaved"})

_OFF_ALIASES = frozenset(
    {"off", "disabled", "disable", "false", "none", "no", "never"}
)
_ON_ALIASES = frozenset(
    {
        "on",
        "enabled",
        "enable",
        "true",
        "force",
        "forced",
        "required",
        "must",
        "static",
        "thinking",
    }
)
_AUTO_ALIASES = frozenset({"auto", "automatic"})
_INTERLEAVED_ALIASES = frozenset({"interleaved", "adaptive"})

_THINKING_BLOCK_OPEN = "<entml:thinking>"
_THINKING_BLOCK_CLOSE = "</entml:thinking>"


def normalize_thinking_mode(mode: Any) -> Optional[str]:
    """将外界声明归一化为 off | on | auto | interleaved；无法识别时返回 None。"""
    if mode is None:
        return None
    key = str(mode).strip().lower()
    if not key:
        return None
    if key in _OFF_ALIASES:
        return "off"
    if key in _ON_ALIASES:
        return "on"
    if key in _AUTO_ALIASES:
        return "auto"
    if key in _INTERLEAVED_ALIASES:
        return "interleaved"
    if key in _CANONICAL_MODES:
        return key
    return None


def _policy_header(mode: str) -> str:
    labels = {
        "off": "off (forced no thinking)",
        "on": "on (forced thinking)",
        "auto": "auto (model decides)",
        "interleaved": "interleaved (thinking after tool results)",
    }
    return (
        f"The thinking_mode for this request is {labels[mode]}. "
        f"Follow the rules below exactly."
    )


def _prompt_off() -> list[str]:
    return [
        _policy_header("off"),
        "",
        "You must NOT output any thinking blocks in this response.",
        f"Do not write `{_THINKING_BLOCK_OPEN}` or `{_THINKING_BLOCK_CLOSE}`.",
        "Respond with only the visible answer text and any "
        "`<entml:function_calls>` blocks if tools are needed.",
    ]


def _prompt_on() -> list[str]:
    return [
        _policy_header("on"),
        "",
        "You MUST output a thinking block before any other content.",
        "At the very start of your response, output:",
        "",
        _THINKING_BLOCK_OPEN,
        "...your reasoning here...",
        _THINKING_BLOCK_CLOSE,
        "",
        "Only after that block, output your visible reply and/or "
        "`<entml:function_calls>`. Never skip the thinking block.",
    ]


def _prompt_auto() -> list[str]:
    return [
        _policy_header("auto"),
        "",
        "Thinking blocks are optional but encouraged when they would help.",
        "At the very start of your response, think carefully about whether "
        f"a `{_THINKING_BLOCK_OPEN}` `{_THINKING_BLOCK_CLOSE}` block would be "
        "appropriate and strongly prefer to output one if you are uncertain.",
    ]


def _prompt_interleaved() -> list[str]:
    return [
        _policy_header("interleaved"),
        "",
        "Thinking blocks are optional at the start, but after function results "
        "you should strongly consider outputting a thinking block before continuing.",
        "Example:",
        "",
        "<entml:function_calls>",
        "...",
        "</entml:function_calls>",
        "",
        "<function_results>",
        "...",
        "</function_results>",
        "",
        _THINKING_BLOCK_OPEN,
        "...thinking about results...",
        _THINKING_BLOCK_CLOSE,
        "",
        "At the very start of your response, think carefully about whether "
        f"a `{_THINKING_BLOCK_OPEN}` `{_THINKING_BLOCK_CLOSE}` block would be "
        "appropriate and strongly prefer to output one if you are uncertain.",
    ]


def build_entml_thinking_section(
    protocol_options: Optional[Dict[str, Any]] = None,
) -> str:
    """按 thinking_mode 构建思考链指令块（off / on / auto / interleaved）。"""
    opts = protocol_options or {}
    mode = normalize_thinking_mode(opts.get("thinking_mode"))
    max_thinking_length = opts.get("max_thinking_length")

    if mode is None and max_thinking_length is None:
        return ""

    lines: list[str] = []
    if mode is not None:
        lines.append(f"<entml:thinking_mode>{mode}</entml:thinking_mode>")
    if max_thinking_length is not None:
        lines.append(
            f"<entml:max_thinking_length>{int(max_thinking_length)}</entml:max_thinking_length>"
        )

    if mode == "off":
        lines.extend([""] + _prompt_off())
    elif mode == "on":
        lines.extend([""] + _prompt_on())
    elif mode == "auto":
        lines.extend([""] + _prompt_auto())
    elif mode == "interleaved":
        lines.extend([""] + _prompt_interleaved())

    return "\n".join(lines)
