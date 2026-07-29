from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from .entml_values import coerce_entml_parameter_value

BLOCK_RE = re.compile(
    r"<entml:invoke\b[^>]*>[\s\S]*?</entml:invoke>",
    re.DOTALL,
)
# 允许 name 前后有其它属性；单/双引号均可。
INVOKE_RE = re.compile(
    r"<entml:invoke\b([^>]*)>([\s\S]*?)</entml:invoke>",
    re.DOTALL,
)
# 允许 name / type 等属性任意顺序；单/双引号均可。
# 闭合标签后必须是下一 parameter / invoke 结束 / parameters 结束。
# 批量解析允许参数块在 body 末尾（$）；流式未闭合 invoke 不允许 $，避免 chunk 落在假闭合上误判。
# 模型偶发省略 entml: 前缀：<parameter name="...">...</parameter>
_BARE_PARAM_OPEN_TAG = r"<parameter\b(?![s>])"
PARAM_OPEN_PATTERN = rf"(?:<entml:parameter\b|{_BARE_PARAM_OPEN_TAG})"
PARAM_CLOSE_ENTML = "</entml:parameter>"
PARAM_CLOSE_BARE = "</parameter>"
# 闭合标签后必须是 invoke 内合法兄弟节点（含裸 description/timeout 等）。
_INVOKE_SIBLING_OPEN = r"<entml:(?!parameter\b|parameters\b|invoke\b)\w+\b"
_PARAM_CLOSE_FOLLOWERS = rf"(?:{PARAM_OPEN_PATTERN}|{_INVOKE_SIBLING_OPEN}|</entml:invoke>|</entml:parameters>|{re.escape(PARAM_CLOSE_BARE)})"
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
# invoke 内裸子标签（非 parameter 包裹），如 Claude Code 输出的 description/timeout。
BARE_INVOKE_CHILD_RE = re.compile(
    r"<entml:(description|timeout)>([\s\S]*?)</entml:\1>",
    re.DOTALL | re.IGNORECASE,
)
BARE_INVOKE_CHILD_OPEN_RE = re.compile(
    r"<entml:(description|timeout)>([\s\S]*)",
    re.DOTALL | re.IGNORECASE,
)
# invoke 内直接子元素：<pattern>v</pattern>、<-n>true</-n>（标签名即参数名）
_INVOKE_DIRECT_TAG_NAME = r"(?:-\w+|[a-zA-Z_][\w.-]*)"
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
# 工具相关外壳 / 残留（不含 thinking，留给 split_entml_thinking）。
_TOOL_WRAPPER_PAIR_RE = re.compile(
    r"<entml:function_calls\b[^>]*>[\s\S]*?</entml:function_calls>",
    re.DOTALL,
)
# 旧版 function_calls 外壳（提示词已不再要求；流式/解析前静默剥离完整开闭标签）。
_LEGACY_WRAPPER_OPEN_RE = re.compile(
    r"<entml:function_calls\b[^>]*>\s*",
    re.IGNORECASE,
)
_LEGACY_WRAPPER_CLOSE_RE = re.compile(
    r"\s*</entml:function_calls\s*>",
    re.IGNORECASE,
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
_PLACEHOLDER_INVOKE_NAMES = frozenset({"$FUNCTION_NAME", "$FUNCTION_NAME2"})


def is_placeholder_invoke_name(name: str) -> bool:
    """提示词占位符（如 ``$FUNCTION_NAME``）不算真实工具调用。"""
    n = (name or "").strip()
    return not n or "$" in n


def entml_invoke_open_is_actionable(buffer: str, pos: int) -> bool:
    """``pos`` 处 ``<entml:invoke`` 是否为已闭合且含真实 name 的工具开标签。"""
    if pos < 0 or not buffer.startswith(_INVOKE_OPEN_PREFIX, pos):
        return False
    gt = buffer.find(">", pos + len(_INVOKE_OPEN_PREFIX))
    if gt < 0:
        return False
    attrs = buffer[pos + len(_INVOKE_OPEN_PREFIX) : gt]
    name = extract_attr_value(attrs, "name")
    if not name:
        return False
    name = normalize_entml_name(name)
    return bool(name) and not is_placeholder_invoke_name(name)


def entml_invoke_open_may_be_streaming(buffer: str, pos: int) -> bool:
    """``pos`` 处 ``<entml:invoke`` 是否仍可能长成真实工具开标签（非 prose 提及）。"""
    if pos < 0 or not buffer.startswith(_INVOKE_OPEN_PREFIX, pos):
        return False
    if entml_invoke_open_is_actionable(buffer, pos):
        return True
    gt = buffer.find(">", pos + len(_INVOKE_OPEN_PREFIX))
    if gt < 0:
        return True
    return False


def _strip_orphan_invoke_tags(content: str) -> str:
    """仅剥离带真实 name 的 invoke 孤儿标签；保留 prose 中的 ``<entml:invoke>`` 提及。"""
    pattern = re.compile(r"</?entml:invoke\b[^>]*/?>", re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if tag.startswith("</"):
            return ""
        if entml_invoke_open_is_actionable(content, match.start()):
            return ""
        return tag

    return pattern.sub(repl, content)


def _strip_orphan_non_invoke_tool_tags(content: str) -> str:
    return re.sub(
        r"</?entml:(?:function_calls|parameter|parameters)\b[^>]*/?>",
        "",
        content,
        flags=re.DOTALL,
    )


_FOLLOWER_PREFIXES = (
    "<entml:parameter",
    "<parameter",
    "</entml:invoke",
    "</entml:parameters",
    "</parameter",
    "<entml:description",
    "<entml:timeout",
)


def parameter_close_at(body: str, close_pos: int) -> int:
    """``close_pos`` 处 parameter 闭合标签的字节长度（entml 或 bare）。"""
    if body.startswith(PARAM_CLOSE_ENTML, close_pos):
        return len(PARAM_CLOSE_ENTML)
    if body.startswith(PARAM_CLOSE_BARE, close_pos):
        if close_pos >= len("</entml:") and body.startswith(
            PARAM_CLOSE_ENTML, close_pos - len("</entml:")
        ):
            return 0
        return len(PARAM_CLOSE_BARE)
    return 0


def _parameter_close_follower_ok(after: str, *, allow_end: bool) -> bool:
    stripped = after.lstrip()
    if not stripped:
        return allow_end
    for prefix in _FOLLOWER_PREFIXES:
        if stripped.startswith(prefix) or prefix.startswith(stripped):
            return True
    return False


_PARAM_OPEN_TAG_RE = re.compile(rf"{PARAM_OPEN_PATTERN}([^>]*)>", re.IGNORECASE)
_MANGLED_PARAM_JSON_TAIL_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"timeout"\s*:\s*(\d+)\s*\}\}?\s*$',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_START_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_EARLY_RE = re.compile(
    r'"\s*,\s*"(?:description|timeout)\b',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE = re.compile(
    r'"\s*,\s*"(?:d|t)',
    re.DOTALL,
)


_MANGLED_PARAM_JSON_COMMA_QUOTE_END_RE = re.compile(
    r'"\s*,\s*"$',
    re.DOTALL,
)
_MANGLED_PARAM_JSON_COMMA_AFTER_QUOTE_RE = re.compile(
    r'"\s*,\s*$',
    re.DOTALL,
)


def mangled_json_param_tail_in_progress(value: str) -> bool:
    """parameter 值中出现误写入 JSON 尾缀但尚未收齐时不应继续增长 partial_json。"""
    return bool(value and _MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE.search(value))


def split_mangled_json_param_tail(value: str) -> Tuple[str, Dict[str, Any]]:
    """模型把 ``", "description": ..., "timeout": ...}}`` 误写入 parameter 值时的拆分。"""
    if not value:
        return value, {}
    match = _MANGLED_PARAM_JSON_TAIL_RE.search(value)
    if match:
        command = value[: match.start() + 1]
        extra: Dict[str, Any] = {
            "description": match.group(1),
            "timeout": int(match.group(2)),
        }
        return command, extra
    partial = _MANGLED_PARAM_JSON_TAIL_START_RE.search(value)
    if partial:
        return value[: partial.start() + 1], {}
    early = _MANGLED_PARAM_JSON_TAIL_EARLY_RE.search(value)
    if early:
        return value[: early.start() + 1], {}
    if _MANGLED_PARAM_JSON_TAIL_IN_PROGRESS_RE.search(value):
        matches = list(re.finditer(r'"\s*,\s*"', value))
        if matches:
            return value[: matches[-1].start() + 1], {}
    comma_quote_end = _MANGLED_PARAM_JSON_COMMA_QUOTE_END_RE.search(value)
    if comma_quote_end:
        return value[: comma_quote_end.start() + 1], {}
    comma_after_quote = _MANGLED_PARAM_JSON_COMMA_AFTER_QUOTE_RE.search(value)
    if comma_after_quote:
        return value[: comma_after_quote.start() + 1], {}
    return value, {}


def synthetic_close_invoke_body(inner: str) -> str:
    """为 force_close / invoke 已闭合但未闭合的 parameter 补齐结构闭合标签。"""
    if not inner:
        return inner
    closed = inner
    if "<entml:parameters>" in closed and "</entml:parameters>" not in closed:
        closed = closed + "</entml:parameters>"
    matches = list(_PARAM_OPEN_TAG_RE.finditer(closed))
    if matches:
        last = matches[-1]
        after = closed[last.end() :]
        open_snip = closed[last.start() : last.end()].lower()
        if open_snip.startswith("<parameter") and not open_snip.startswith("<entml:"):
            need = PARAM_CLOSE_BARE
        else:
            need = PARAM_CLOSE_ENTML
        if need not in after and find_valid_parameter_close(closed, last.end(), allow_end=True) < 0:
            closed = closed + need
    return closed


def find_valid_parameter_close(body: str, search_from: int = 0, *, allow_end: bool = True) -> int:
    """返回 parameter 闭合标签在 ``body`` 中的起始下标；忽略参数值内的假闭合。"""
    pos = search_from
    while pos < len(body):
        next_entml = body.find(PARAM_CLOSE_ENTML, pos)
        next_bare = body.find(PARAM_CLOSE_BARE, pos)
        if next_entml < 0 and next_bare < 0:
            return -1
        candidates = []
        if next_entml >= 0:
            candidates.append(next_entml)
        if next_bare >= 0 and parameter_close_at(body, next_bare) > 0:
            candidates.append(next_bare)
        if not candidates:
            pos = min(x for x in (next_entml, next_bare) if x >= 0) + 1
            continue
        close = min(candidates)
        close_len = parameter_close_at(body, close)
        after = body[close + close_len :]
        if _parameter_close_follower_ok(after, allow_end=allow_end):
            return close
        pos = close + 1
    return -1


def extract_attr_value(attrs: str, attr_name: str = "name") -> Optional[str]:
    """从标签属性串中提取 name/type 等（支持单双引号）。"""
    if not attrs:
        return None
    if attr_name == "name":
        match = _ATTR_NAME_RE.search(attrs)
    elif attr_name == "type":
        match = _PARAM_TYPE_ATTR_RE.search(attrs)
    else:
        pattern = re.compile(
            rf"""\b{re.escape(attr_name)}\s*=\s*(?P<q>["'])(?P<v>.*?)(?P=q)"""
        )
        match = pattern.search(attrs)
    if not match:
        return None
    return match.group("v").strip()


def normalize_entml_name(name: str) -> str:
    """还原 markdown 转义下划线等常见名称噪声。"""
    if not name:
        return ""
    return name.replace("\\_", "_").replace("\\-", "-").strip()


def extract_parameter_type_attr(attrs: str) -> Optional[str]:
    """从 parameter 开标签属性中提取 type=\"...\"。"""
    return extract_attr_value(attrs or "", "type")


def parse_sub_tags(
    content: str,
    schema_index: Optional[Dict[str, Any]] = None,
    func_name: str = "",
) -> Dict[str, Any]:
    """解析 <entml:parameters> 内的子标签，返回参数字典。"""
    args: Dict[str, Any] = {}
    for m in SUB_TAG_RE.finditer(content):
        pname = m.group(1).strip()
        pval = m.group(2).strip()
        pschema = schema_index.get(func_name, {}).get(pname, {}) if schema_index else {}
        args[pname] = coerce_entml_parameter_value(pval, pschema or None)
    return args


def strip_legacy_function_calls_wrapper(text: str) -> str:
    """移除完整 legacy ``<entml:function_calls>`` 开/闭标签（裸 invoke 为一等格式）。"""
    if not text:
        return text
    out = _LEGACY_WRAPPER_OPEN_RE.sub("", text)
    out = _LEGACY_WRAPPER_CLOSE_RE.sub("", out)
    return out


def strip_tool_entml_residue(content: str) -> str:
    """剥离工具相关 entml 标签残留，保留 thinking 与非工具 prose 提及。"""
    if not content:
        return content
    cleaned = _TOOL_WRAPPER_PAIR_RE.sub("", content)
    cleaned = BLOCK_RE.sub("", cleaned)
    cleaned = _strip_orphan_invoke_tags(cleaned)
    cleaned = _strip_orphan_non_invoke_tool_tags(cleaned)
    cleaned = _EMPTY_FENCE_RE.sub("", cleaned)
    cleaned = _FENCE_ONLY_LINE_RE.sub("", cleaned)
    # 折叠因剥离产生的多余空行
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
