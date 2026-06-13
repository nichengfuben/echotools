from __future__ import annotations

"""标识符生成工具。"""

import secrets
import struct
import time
import uuid

__all__ = ["uuid7", "short_id", "trace_id", "span_id"]


def uuid7() -> str:
    """生成时间有序的 UUIDv7 字符串。

    Returns:
        符合 UUIDv7 位布局的字符串。
    """
    ts_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand_bytes = secrets.token_bytes(10)
    rand_a = struct.unpack(">H", rand_bytes[:2])[0] & 0x0FFF
    rand_b = struct.unpack(">Q", rand_bytes[2:])[0] & 0x3FFFFFFFFFFFFFFF
    uuid_int = (
        ts_ms << 80
        | 0x7 << 76
        | rand_a << 64
        | 0b10 << 62
        | rand_b
    )
    return str(uuid.UUID(int=uuid_int))


def short_id(length: int = 12) -> str:
    """生成短随机 ID。

    Args:
        length: 长度，默认为 12。

    Returns:
        十六进制随机字符串。
    """
    if length <= 0:
        raise ValueError("length 必须为正整数")
    return uuid.uuid4().hex[:length]


def trace_id() -> str:
    """生成 trace_id（32 位十六进制）。

    Returns:
        trace_id 字符串。
    """
    return secrets.token_hex(16)


def span_id() -> str:
    """生成 span_id（16 位十六进制）。

    Returns:
        span_id 字符串。
    """
    return secrets.token_hex(8)
