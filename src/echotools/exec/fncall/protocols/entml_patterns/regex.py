from __future__ import annotations

import re

BLOCK_RE = re.compile(
    r"<entml:invoke\b[^>]*>[\s\S]*?</entml:invoke>",
    re.DOTALL,
)
INVOKE_RE = re.compile(
    r"<entml:invoke\b([^>]*)>([\s\S]*?)</entml:invoke>",
    re.DOTALL,
)
_INVOKE_DIRECT_TAG_NAME = r"(?:-\w+|[a-zA-Z_][\w.-]*)"
_BARE_PARAM_OPEN_TAG = r"<parameter\b(?![s>])"
PARAM_OPEN_PATTERN = rf"(?:<entml:parameter\b|{_BARE_PARAM_OPEN_TAG})"
PARAM_CLOSE_ENTML = "</entml:parameter>"
PARAM_CLOSE_BARE = "</parameter>"
_INVOKE_SIBLING_OPEN = r"<entml:(?!parameter\b|parameters\b|invoke\b)\w+\b"
_INVOKE_DIRECT_CHILD_OPEN = rf"<(?!entml:)({_INVOKE_DIRECT_TAG_NAME})\b"
_PARAM_CLOSE_FOLLOWERS = (
    rf"(?:{PARAM_OPEN_PATTERN}|{_INVOKE_SIBLING_OPEN}|{_INVOKE_DIRECT_CHILD_OPEN}"
    rf"|</entml:invoke>|</entml:parameters>|{re.escape(PARAM_CLOSE_BARE)})"
)
_PARAM_CLOSE_LOOKAHEAD = rf"(?=\s*{_PARAM_CLOSE_FOLLOWERS})"
_PARAM_CLOSE_LOOKAHEAD_EOL = rf"(?=\s*(?:{_PARAM_CLOSE_FOLLOWERS}|$))"
PARAM_RE = re.compile(
    rf"{PARAM_OPEN_PATTERN}([^>]*)>([\s\S]*?)(?:{re.escape(PARAM_CLOSE_ENTML)}|{re.escape(PARAM_CLOSE_BARE)}){_PARAM_CLOSE_LOOKAHEAD_EOL}",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_CLOSE_VALID_RE = re.compile(
    rf"</entml:parameter>{_PARAM_CLOSE_LOOKAHEAD_EOL}",
    re.IGNORECASE,
)
_PARAM_CLOSE_VALID_STREAM_RE = re.compile(
    rf"</entml:parameter>{_PARAM_CLOSE_LOOKAHEAD}",
    re.IGNORECASE,
)
_ATTR_NAME_RE = re.compile(
    r"""\bname\s*=\s*(?P<q>["'])(?P<v>.*?)(?P=q)""",
    re.DOTALL,
)
_PARAM_TYPE_ATTR_RE = re.compile(
    r"""\btype\s*=\s*(?P<q>["'])(?P<v>.*?)(?P=q)"""
)
PARAMETERS_RE = re.compile(
    r"<entml:parameters>([\s\S]*?)</entml:parameters>",
    re.DOTALL,
)
BARE_INVOKE_CHILD_RE = re.compile(
    r"<entml:(description|timeout)>([\s\S]*?)</entml:\1>",
    re.DOTALL | re.IGNORECASE,
)
BARE_INVOKE_CHILD_OPEN_RE = re.compile(
    r"<entml:(description|timeout)>([\s\S]*)",
    re.DOTALL | re.IGNORECASE,
)
INVOKE_DIRECT_CHILD_RE = re.compile(
    rf"<(?!entml:)({_INVOKE_DIRECT_TAG_NAME})>([\s\S]*?)</\1>",
    re.DOTALL,
)
INVOKE_DIRECT_CHILD_OPEN_RE = re.compile(
    rf"<(?!entml:)({_INVOKE_DIRECT_TAG_NAME})>([\s\S]*)",
    re.DOTALL,
)
INVOKE_DIRECT_CHILD_SKIP = frozenset({"parameter", "parameters"})
SUB_TAG_RE = re.compile(
    r"<([^>]+)>([\s\S]*?)</\1>",
    re.DOTALL,
)
_TOOL_WRAPPER_PAIR_RE = re.compile(
    r"<entml:function_calls\b[^>]*>[\s\S]*?</entml:function_calls>",
    re.DOTALL,
)
_TOOL_ORPHAN_TAG_RE = re.compile(
    r"</?entml:(?:function_calls|invoke|parameter|parameters)\b[^>]*/?>",
    re.DOTALL,
)
_EMPTY_FENCE_RE = re.compile(
    r"```(?:xml|entml|text)?\s*```",
    re.IGNORECASE,
)
_FENCE_ONLY_LINE_RE = re.compile(
    r"^\s*```(?:xml|entml|text)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_INVOKE_OPEN_PREFIX = "<entml:invoke"
_INVOKE_CLOSE = "</entml:invoke>"
_PLACEHOLDER_INVOKE_NAMES = frozenset({"$FUNCTION_NAME", "$FUNCTION_NAME2"})
_FOLLOWER_PREFIXES = (
    "<entml:parameter",
    "<parameter",
    "</entml:invoke",
    "</entml:parameters",
    "</parameter",
    "<entml:description",
    "<entml:timeout",
    "<",
)
_PARAM_OPEN_TAG_RE = re.compile(rf"{PARAM_OPEN_PATTERN}([^>]*)>", re.IGNORECASE)
