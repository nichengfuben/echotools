"""Entml thinking: prompt section, history blocks, stream parsing."""

from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_section,
    is_thinking_enabled,
    parse_max_thinking_length,
)
from echotools.exec.fncall.protocols.entml_think.hist import (
    apply_thinking_history_policy,
    extract_reasoning_text,
    format_entml_thinking_history_block,
    parse_include_thinking_in_history,
    parse_interleaved_history,
)
from echotools.exec.fncall.protocols.entml_think.parse import (
    EntmlThinkingStreamFilter,
    has_unclosed_entml_thinking,
    split_entml_thinking,
)

__all__ = [
    "EntmlThinkingStreamFilter",
    "apply_thinking_history_policy",
    "build_entml_thinking_section",
    "extract_reasoning_text",
    "format_entml_thinking_history_block",
    "has_unclosed_entml_thinking",
    "is_thinking_enabled",
    "parse_include_thinking_in_history",
    "parse_interleaved_history",
    "parse_max_thinking_length",
    "split_entml_thinking",
]
