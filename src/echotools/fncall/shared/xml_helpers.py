"""Shared XML utilities for fncall protocols.

CDATA extraction, XML attribute escaping, and common regex patterns.
"""

from __future__ import annotations

import re

# CDATA 提取
_CDATA_RE = re.compile(r'<!\[CDATA\[([\s\S]*?)\]\]>')

# XML 属性转义
_XML_ESCAPE_MAP = {
    '&': '&amp;',
    '"': '&quot;',
    "'": '&apos;',
    '<': '&lt;',
    '>': '&gt;',
}


def extract_cdata(value: str) -> str:
    """从 CDATA 或纯文本中提取值。"""
    cdata = _CDATA_RE.search(value)
    if cdata:
        return cdata.group(1).strip()
    return value.strip()


def escape_xml_attr(value: str) -> str:
    """转义 XML 属性值。"""
    for char, escape in _XML_ESCAPE_MAP.items():
        value = value.replace(char, escape)
    return value


# ---------------------------------------------------------------------------
# <|PROVIDER| protocol regex patterns
# ---------------------------------------------------------------------------

_PROVIDER_START = "<|PROVIDER|tool_calls>"
_PROVIDER_END = "</|PROVIDER|tool_calls>"

_PROVIDER_BLOCK_RE = re.compile(
    r'<\|PROVIDER\|tool_calls>([\s\S]*?)</\|PROVIDER\|tool_calls>',
    re.DOTALL,
)
_PROVIDER_INVOKE_RE = re.compile(
    r'<\|PROVIDER\|invoke\s+name="([^"]+)"\s*>([\s\S]*?)</\|PROVIDER\|invoke>',
    re.DOTALL,
)
_PROVIDER_PARAM_RE = re.compile(
    r'<\|PROVIDER\|parameter\s+name="([^"]+)"\s*>([\s\S]*?)</\|PROVIDER\|parameter>',
    re.DOTALL,
)
