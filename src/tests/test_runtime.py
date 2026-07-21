from __future__ import annotations

from echotools.plat.runtime import RuntimeCollector


async def test_runtime_collector_sync_and_async() -> None:
    rc = RuntimeCollector("svc")

    rc.register("sync", lambda: {"ok": True})

    async def async_collector() -> dict:
        return {"async": True}

    rc.register("async", async_collector)

    async def failing() -> dict:
        raise RuntimeError("fail")

    rc.register("bad", failing)

    result = await rc.collect()
    assert result["service"] == "svc"
    assert result["sync"] == {"ok": True}
    assert result["async"] == {"async": True}
    assert "error" in result["bad"]
