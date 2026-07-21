from __future__ import annotations

import asyncio

import pytest

from echotools import EchoTools
from echotools.plat.sdk.facade import EchoTools as EchoToolsDirect


async def test_enabled_modules_blocks_access() -> None:
    et = EchoTools(enabled_modules=frozenset({"logger"}))
    et.logger.configure(level="INFO")
    with pytest.raises(RuntimeError, match="disabled"):
        _ = et.config


async def test_cache_cleanup_loop(tmp_path) -> None:
    et = EchoTools(
        service_name="test",
        persist_dir=str(tmp_path),
        cache_cleanup_interval=0.05,
    )
    et.cache.set("k", "v", ttl=0.01)
    await et.startup()
    await asyncio.sleep(0.08)
    await et.shutdown()


def test_repr_shows_initialized(tmp_path) -> None:
    et = EchoToolsDirect(service_name="x", persist_dir=str(tmp_path))
    _ = et.logger
    assert "logger" in repr(et)
