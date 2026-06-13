from __future__ import annotations

import pytest

from echotools.cache import MemoryCache
from echotools.retry import retry_with_backoff


def test_memory_cache_ttl() -> None:
    """缓存读写与删除。"""
    c = MemoryCache()
    c.set("k", 1)
    assert c.get("k") == 1
    c.delete("k")
    assert c.get("k") is None


@pytest.mark.asyncio
async def test_retry_succeeds_after_failures() -> None:
    """重试在失败后成功。"""
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("fail")
        return "ok"

    result = await retry_with_backoff(
        flaky, max_attempts=5, base_delay=0.01
    )
    assert result == "ok"
    assert calls["n"] == 3
