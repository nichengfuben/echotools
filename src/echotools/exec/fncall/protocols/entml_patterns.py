from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .entml_values import coerce_entml_parameter_value

BLOCK_RE = re.compile(
    r"<entml:function_calls\b[^>]*>([\s\S]*?)</entml:function_calls>",
    re.DOTALL,
)
INVOKE_RE = re.compile(
    r'<entml:invoke\s+name="([^"]+)">\s*([\s\S]*?)\s*</entml:invoke>',
    re.DOTALL,
)
PARAM_RE = re.compile(
    r'<entml:parameter\s+name="([^"]+)"([^>]*)>\s*([\s\S]*?)\s*</entml:parameter>',
    re.DOTALL,
)
_PARAM_TYPE_ATTR_RE = re.compile(r'\btype="([^"]+)"')
PARAMETERS_RE = re.compile(
    r'<entml:parameters>([\s\S]*?)</entml:parameters>',
    re.DOTALL,
)
SUB_TAG_RE = re.compile(
    r'<([^>]+)>([\s\S]*?)</\1>',
    re.DOTALL,
)


def extract_parameter_type_attr(attrs: str) -> Optional[str]:
    """从 parameter 开标签属性中提取 type=\"...\"。"""
    match = _PARAM_TYPE_ATTR_RE.search(attrs or "")
    if not match:
        return None
    return match.group(1).strip()


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
