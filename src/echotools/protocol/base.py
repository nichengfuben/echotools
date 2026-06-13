from __future__ import annotations

"""协议适配器抽象基类 + 注册表。"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from echotools.logger.manager import get_logger

__all__ = [
    "ToolProtocol",
    "register_protocol",
    "get_protocol_by_id",
    "list_protocols",
    "VALID_PROTOCOL_IDS",
]

logger = get_logger(__name__)

VALID_PROTOCOL_IDS = (
    "xml",
    "antml",
    "original",
    "bracket",
    "nous",
    "custom",
)


class ToolProtocol(ABC):
    """工具调用协议适配器抽象基类。"""

    @property
    @abstractmethod
    def id(self) -> str:
        """协议 ID。"""
        ...

    def get_trigger_tags(self) -> List[str]:
        """触发标记列表。"""
        return []

    @abstractmethod
    def render_prompt(
        self,
        tool_descs: str,
        lang: str,
        user_system_prompt: str = "",
        history_text: str = "",
        loop_warning: str = "",
        current_user_message: str = "",
    ) -> str:
        """构建注入工具定义的 prompt。"""
        ...

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        """检测触发标记。"""
        return (False, -1)

    @abstractmethod
    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """提取工具调用。"""
        ...

    @abstractmethod
    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """解析完整协议片段。"""
        ...

    def clean_tags(self, content: str) -> str:
        """移除协议标签残留。"""
        return content.strip()

    def format_assistant_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> str:
        """渲染工具调用为协议格式。"""
        return ""

    def format_tool_result(
        self,
        content: str,
        tool_name: str = "",
        is_error: bool = False,
    ) -> str:
        """渲染工具结果为协议格式。"""
        return ""

    def supports_streaming(self) -> bool:
        """是否支持流式检测。"""
        return True


_PROTOCOL_REGISTRY: Dict[str, ToolProtocol] = {}


def register_protocol(protocol: ToolProtocol) -> None:
    """注册协议实现。"""
    _PROTOCOL_REGISTRY[protocol.id] = protocol
    logger.debug("已注册协议: %s", protocol.id)


def get_protocol_by_id(protocol_id: str) -> ToolProtocol:
    """按 ID 获取协议。"""
    if protocol_id not in _PROTOCOL_REGISTRY:
        available = ", ".join(sorted(_PROTOCOL_REGISTRY.keys()))
        raise ValueError(
            "未知协议: {!r}（可用: {}）".format(protocol_id, available)
        )
    return _PROTOCOL_REGISTRY[protocol_id]


def list_protocols() -> List[str]:
    """全部已注册协议 ID。"""
    return sorted(_PROTOCOL_REGISTRY.keys())
