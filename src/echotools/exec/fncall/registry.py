from __future__ import annotations

"""协议注册 + 获取（无全局配置依赖）。"""

from typing import Dict, Optional

from echotools.base.logger.manager import get_logger
from echotools.exec.protocol.base import (
    _PROTOCOL_REGISTRY,
    ToolProtocol,
    get_protocol_by_id,
)

__all__ = ["get_protocol", "list_protocols"]

logger = get_logger(__name__)

_registered = False
_mapping_logged: set = set()


def _ensure_registered() -> None:
    """确保内置协议已注册。"""
    global _registered
    if _registered:
        return
    from echotools.exec.fncall.protocols import _register_all

    _register_all()
    _registered = True


def get_protocol(
    protocol_id: str = "",
    *,
    default_protocol: str = "entml",
    platform_id: str = "",
    mapping: Optional[Dict[str, str]] = None,
) -> ToolProtocol:
    """获取协议实例（完全通过参数，无全局配置）。

    Args:
        protocol_id: 协议 ID。
        default_protocol: 缺省协议。
        platform_id: 平台 ID（用于 mapping 查找）。
        mapping: 平台到协议的映射。

    Returns:
        ToolProtocol 实例。
    """
    if not protocol_id:
        if platform_id and mapping:
            mapped = mapping.get(platform_id)
            if mapped:
                protocol_id = mapped
                key = "{}:{}".format(platform_id, protocol_id)
                if key not in _mapping_logged:
                    logger.debug(
                        "平台 %s 映射到协议 %s",
                        platform_id,
                        protocol_id,
                    )
                    _mapping_logged.add(key)
    if not protocol_id:
        protocol_id = default_protocol
    _ensure_registered()
    return get_protocol_by_id(protocol_id)


def list_protocols() -> list:
    """全部协议 ID。"""
    _ensure_registered()
    return sorted(_PROTOCOL_REGISTRY.keys())
