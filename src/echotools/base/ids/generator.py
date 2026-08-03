from __future__ import annotations

"""标识符生成工具。"""

import secrets
import struct
import time
import uuid

__all__ = ["uuid7", "short_id", "trace_id", "span_id", "gen_tool_id"]


def uuid7() -> str:
    """时间有序的 UUIDv7。"""
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
    if length <= 0:
        raise ValueError("length 必须为正整数")
    return uuid.uuid4().hex[:length]


def trace_id() -> str:
    return secrets.token_hex(16)


def span_id() -> str:
    return secrets.token_hex(8)


def gen_tool_id() -> str:
    """Anthropic 兼容 tool_use id（``toolu_`` + 24 hex）。"""
    return f"toolu_{uuid.uuid4().hex[:24]}"
