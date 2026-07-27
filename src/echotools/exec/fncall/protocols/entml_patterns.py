from __future__ import annotations

import re
from typing import Any, Dict, Optional

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
PARAM_RE = re.compile(
    r"<entml:parameter\b([^>]*)>([\s\S]*?)</entml:parameter>",
    re.DOTALL,
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
    """剥离工具相关 entml 标签残留，保留 thinking 等非工具标签。"""
    if not content:
        return content
    cleaned = _TOOL_WRAPPER_PAIR_RE.sub("", content)
    cleaned = BLOCK_RE.sub("", cleaned)
    cleaned = _TOOL_ORPHAN_TAG_RE.sub("", cleaned)
    cleaned = _EMPTY_FENCE_RE.sub("", cleaned)
    cleaned = _FENCE_ONLY_LINE_RE.sub("", cleaned)
    # 折叠因剥离产生的多余空行
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
