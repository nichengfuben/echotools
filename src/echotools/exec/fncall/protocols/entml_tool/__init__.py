"""Tool invoke/format helpers for entml protocol."""
from __future__ import annotations

from .blocks import parse_tool_block_body, parse_tool_block_calls, strip_tool_block_spans
from .comment import (
    leading_partial_tool_result_id_comment_len,
    strip_complete_tool_result_id_comments,
    strip_tool_result_id_comments_for_display,
    trailing_partial_tool_result_id_comment_len,
)
from .fakemarkup import (
    leading_partial_fake_entml_structure_len,
    strip_fake_entml_structure_markup,
    strip_fake_entml_structure_markup_for_display,
    strip_orphan_entml_close_tags,
    trailing_partial_fake_entml_structure_len,
)
from .invoke import (
    format_entml_parameter_value,
    format_entml_tool_calls,
    parse_entml_tool_calls,
    parse_invoke_args,
)
from .tools import format_entml_tool_descs
from .values import (
    _coerce_entml_arg_value,
    coerce_entml_arguments,
    coerce_entml_parameter_value,
    effective_entml_param_json_type,
    resolve_entml_parameter_schema,
)

__all__ = [
    "_coerce_entml_arg_value",
    "coerce_entml_arguments",
    "coerce_entml_parameter_value",
    "effective_entml_param_json_type",
    "format_entml_parameter_value",
    "format_entml_tool_calls",
    "format_entml_tool_descs",
    "leading_partial_fake_entml_structure_len",
    "leading_partial_tool_result_id_comment_len",
    "parse_entml_tool_calls",
    "parse_invoke_args",
    "parse_tool_block_body",
    "parse_tool_block_calls",
    "resolve_entml_parameter_schema",
    "strip_complete_tool_result_id_comments",
    "strip_fake_entml_structure_markup",
    "strip_fake_entml_structure_markup_for_display",
    "strip_orphan_entml_close_tags",
    "strip_tool_block_spans",
    "strip_tool_result_id_comments_for_display",
    "trailing_partial_fake_entml_structure_len",
    "trailing_partial_tool_result_id_comment_len",
]
