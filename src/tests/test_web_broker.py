from __future__ import annotations

import asyncio

import pytest

from echotools.media.web.broker import RequestBroker
from echotools.media.web.stats import RequestStats, get_stats


@pytest.mark.http
@pytest.mark.asyncio
async def test_request_broker_broadcast() -> None:
    pytest.importorskip("aiohttp")
    broker = RequestBroker()
    loop = asyncio.get_running_loop()
    broker.set_loop(loop)
    await broker.broadcast({"type": "request_end", "id": "1", "status": 200})
    recent = broker.get_recent(10)
    assert len(recent) == 1


def test_request_stats_record() -> None:
    stats = RequestStats()
    stats.record(platform="p", model="m", status=200, latency_ms=12.5)
    data = stats.to_dict()
    assert data["total"] >= 1


def test_get_stats_singleton() -> None:
    assert get_stats() is get_stats()


@pytest.mark.asyncio
async def test_broker_send_history_partial_failure() -> None:
    class FlakyWS:
        def __init__(self) -> None:
            self.calls = 0

        async def send_json(self, data: dict) -> None:
            self.calls += 1
            if self.calls > 1:
                raise ConnectionError("broken")

    broker = RequestBroker()
    await broker.broadcast({"type": "request_end", "id": "1", "status": 200})
    await broker.broadcast({"type": "request_end", "id": "2", "status": 200})
    ws = FlakyWS()
    count = await broker.send_history(ws)
    assert count == 1
