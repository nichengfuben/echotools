from __future__ import annotations

"""fncall 模块导出。"""

from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.parsers.xml_parser import (
    parse_fncall,
    parse_fncall_xml,
)
from echotools.exec.fncall.prompt.inject import inject_fncall
from echotools.exec.fncall.registry import get_protocol, list_protocols
from echotools.exec.fncall.shared.loop_detect import (
    LoopDetectionResult,
    detect_tool_loop,
)
from echotools.exec.fncall.shared.normalization import (
    format_tool_descs,
    normalize_content,
    normalize_tool_call,
    normalize_tool_calls,
)
from echotools.exec.protocol.base import (
    ToolProtocol,
    get_protocol_by_id,
    register_protocol,
)

__all__ = [
    "inject_fncall",
    "parse_fncall",
    "parse_fncall_xml",
    "FncallStreamParser",
    "format_tool_descs",
    "normalize_content",
    "normalize_tool_call",
    "normalize_tool_calls",
    "detect_tool_loop",
    "LoopDetectionResult",
    "ToolProtocol",
    "get_protocol",
    "get_protocol_by_id",
    "register_protocol",
    "list_protocols",
]
