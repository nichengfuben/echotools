from __future__ import annotations

from echotools.lifecycle import LifecycleManager


async def test_lifecycle_startup_shutdown_order() -> None:
    events = []
    lm = LifecycleManager()

    async def on_start() -> None:
        events.append("start")

    async def on_stop() -> None:
        events.append("stop")

    lm.on_startup(on_start)
    lm.on_shutdown(on_stop)
    await lm.startup()
    await lm.shutdown()
    assert events == ["start", "stop"]


async def test_lifecycle_startup_is_idempotent() -> None:
    lm = LifecycleManager()
    count = 0

    def hook() -> None:
        nonlocal count
        count += 1

    lm.on_startup(hook)
    await lm.startup()
    await lm.startup()
    assert count == 1
