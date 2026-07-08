from __future__ import annotations

import time

import pytest

from echotools.cache import ListCache, MemoryCache
from echotools.retry import (
    retry_async_generator,
    retry_on_empty,
    retry_on_exception,
    retry_with_backoff,
)


def test_memory_cache_ttl() -> None:
    c = MemoryCache()
    c.set("k", 1)
    assert c.get("k") == 1
    c.delete("k")
    assert c.get("k") is None


def test_memory_cache_expiry() -> None:
    c = MemoryCache()
    c.set("k", 1, ttl=0.01)
    time.sleep(0.02)
    assert c.get("k") is None


def test_memory_cache_lru_eviction() -> None:
    c = MemoryCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("c", 3)
    assert c.get("a") is None
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_memory_cache_cleanup() -> None:
    c = MemoryCache()
    c.set("k", 1, ttl=0.01)
    time.sleep(0.02)
    assert c.cleanup() == 1


@pytest.mark.asyncio
async def test_list_cache_load_save(tmp_path) -> None:
    cache = ListCache("models", ["a"], str(tmp_path / "list.json"))
    await cache.save(["x", "y"])
    loaded = await cache.load()
    assert loaded == ["x", "y"]


@pytest.mark.asyncio
async def test_list_cache_refresh_merge(tmp_path) -> None:
    cache = ListCache("models", ["a"], str(tmp_path / "list.json"), overwrite=False)
    await cache.save(["a", "b"])

    async def fetch() -> list:
        return ["b", "c"]

    await cache._do_refresh(fetch, None)
    assert cache.items == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_retry_succeeds_after_failures() -> None:
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


@pytest.mark.asyncio
async def test_retry_on_empty() -> None:
    calls = {"n": 0}

    async def sometimes_empty() -> str:
        calls["n"] += 1
        return "ok" if calls["n"] >= 2 else ""

    result = await retry_on_empty(sometimes_empty, max_retries=3)
    assert result == "ok"


@pytest.mark.asyncio
async def test_retry_on_exception_with_callback() -> None:
    retries = []

    async def flaky() -> str:
        if len(retries) < 1:
            retries.append(1)
            raise OSError("temp")
        return "done"

    result = await retry_on_exception(
        flaky,
        max_retries=2,
        exceptions=(OSError,),
        on_retry=lambda i, e: retries.append(i),
    )
    assert result == "done"


@pytest.mark.asyncio
async def test_retry_async_generator() -> None:
    def factory():
        async def gen():
            yield "a"
            yield "b"

        return gen()

    chunks = []
    async for item in retry_async_generator(factory, max_retries=1):
        chunks.append(item)
    assert chunks == ["a", "b"]
