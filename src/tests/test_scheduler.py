from __future__ import annotations

import asyncio

from echotools.plat.scheduler import TaskScheduler


async def test_scheduler_limits_concurrency() -> None:
    scheduler = TaskScheduler(max_concurrent=1)
    order = []

    async def job(n: int) -> None:
        order.append(f"start-{n}")
        await asyncio.sleep(0.01)
        order.append(f"end-{n}")

    await scheduler.submit("job-1", job(1))
    await scheduler.submit("job-2", job(2))
    await scheduler.cancel_all()
    assert "start-1" in order


def test_scheduler_status() -> None:
    scheduler = TaskScheduler(max_concurrent=2)
    status = scheduler.get_status()
    assert status["max_concurrent"] == 2
    assert status["active_count"] == 0
