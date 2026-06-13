from __future__ import annotations

"""协议注册 + 获取（无全局配置依赖）。"""

from typing import Dict, Optional

from echotools.protocol.base import (
    ToolProtocol,
    _PROTOCOL_REGISTRY,
    get_protocol_by_id,
    register_protocol,
)
from echotools.logger.manager import get_logger

__all__ = ["get_protocol", "list_protocols"]

logger = get_logger(__name__)

_custom_instance: Optional[ToolProtocol] = None
_registered = False
_mapping_logged: set = set()


def _get_custom_protocol(
    prompt_en: str = "", prompt_zh: str = ""
) -> ToolProtocol:
    """获取或创建 custom 协议。"""
    global _custom_instance
    if _custom_instance is not None:
        return _custom_instance
    from echotools.fncall.protocols.custom import CustomProtocol

    _custom_instance = CustomProtocol(
        prompt_en=prompt_en, prompt_zh=prompt_zh
    )
    return _custom_instance


def _ensure_registered() -> None:
    """确保内置协议已注册。"""
    global _registered
    if _registered:
        return
    from echotools.fncall.protocols import _register_all

    _register_all()
    _registered = True


def get_protocol(
    protocol_id: str = "",
    *,
    default_protocol: str = "xml",
    custom_prompt_en: str = "",
    custom_prompt_zh: str = "",
    platform_id: str = "",
    mapping: Optional[Dict[str, str]] = None,
) -> ToolProtocol:
    """获取协议实例（完全通过参数，无全局配置）。

    Args:
        protocol_id: 协议 ID。
        default_protocol: 缺省协议。
        custom_prompt_en: custom 英文模板。
        custom_prompt_zh: custom 中文模板。
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
    if protocol_id == "custom":
        return _get_custom_protocol(custom_prompt_en, custom_prompt_zh)
    _ensure_registered()
    return get_protocol_by_id(protocol_id)


def list_protocols() -> list:
    """全部协议 ID。"""
    _ensure_registered()
    return sorted(_PROTOCOL_REGISTRY.keys())
