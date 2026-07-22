from __future__ import annotations

from typing import Any, Dict, Optional


def build_entml_thinking_section(
    protocol_options: Optional[Dict[str, Any]] = None,
) -> str:
    """仅当外界声明 thinking_mode / max_thinking_length 时构建思考链指令块。"""
    opts = protocol_options or {}
    thinking_mode = opts.get("thinking_mode")
    max_thinking_length = opts.get("max_thinking_length")

    if thinking_mode is None and max_thinking_length is None:
        return ""

    lines: list[str] = []
    if thinking_mode is not None:
        mode = str(thinking_mode).strip()
        if mode:
            lines.append(f"<entml:thinking_mode>{mode}</entml:thinking_mode>")
    if max_thinking_length is not None:
        lines.append(
            f"<entml:max_thinking_length>{int(max_thinking_length)}</entml:max_thinking_length>"
        )

    mode_lower = str(thinking_mode or "").strip().lower()
    if mode_lower in ("interleaved", "auto"):
        lines.extend(
            [
                "",
                "If the thinking_mode is interleaved or auto, then after function "
                "results you should strongly consider outputting a thinking block. "
                "Here is an example:",
                "",
                "<entml:function_calls>",
                "...",
                "</entml:function_calls>",
                "",
                "<function_results>",
                "...",
                "</function_results>",
                "",
                "<thinking>",
                "...thinking about results",
                "</thinking>",
                "At the very start of your response, think carefully about whether "
                "a `<thinking>` `</thinking>` block would be appropriate and "
                "strongly prefer to output a thinking block if you are uncertain.",
            ]
        )

    return "\n".join(lines)
