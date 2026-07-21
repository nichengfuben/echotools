from __future__ import annotations

"""Shared HTTP utilities for route handlers.

Protocol-aware: clean_fncall and safe_flush use the active protocol's
tag detection and cleaning logic.
"""

from typing import Any, Tuple

__all__ = ["clean_fncall", "safe_flush", "get_json"]


def clean_fncall(content: str, platform_id: str = "") -> str:
    """使用当前协议或指定平台的协议清理响应中的 fncall 标签。

    Args:
        content: 原始文本。
        platform_id: 可选的平台 ID，用于确定正确的协议。

    Returns:
        清理后的文本。
    """
    from echotools.exec.fncall.registry import get_protocol
    protocol = get_protocol(platform_id=platform_id)
    return protocol.clean_tags(content)


def safe_flush(buffer: str, platform_id: str = "", protocol_id: str = "") -> Tuple[str, str]:
    """提取 buffer 中可安全输出的前缀，保留潜在的协议触发标记尾部。

    Args:
        buffer: 当前文本缓冲区。
        platform_id: 可选的平台 ID，用于确定正确的协议。
        protocol_id: 可选的协议 ID，优先于 platform_id。

    Returns:
        (safe, remain): safe 是可输出前缀，remain 是待保留尾部。
    """
    from echotools.exec.fncall.registry import get_protocol
    protocol = get_protocol(protocol_id=protocol_id, platform_id=platform_id)
    tags = protocol.get_trigger_tags()
    if not tags:
        return buffer, ""

    buf_len = len(buffer)
    max_keep = max(len(t) - 1 for t in tags)
    check_len = min(max_keep, buf_len)
    for length in range(check_len, 0, -1):
        suffix = buffer[buf_len - length:]
        if any(tag.startswith(suffix) and suffix != tag for tag in tags):
            return buffer[:buf_len - length], buffer[buf_len - length:]
    return buffer, ""


async def get_json(request: Any) -> Any:
    """Safely parse request JSON body.

    Args:
        request: aiohttp request object.

    Returns:
        Parsed dict, or None on failure.
    """
    try:
        return await request.json()
    except Exception:
        return None
