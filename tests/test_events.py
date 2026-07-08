from __future__ import annotations

from dataclasses import dataclass

import pytest

from echotools.events import Event, EventBus


@dataclass
class Ping(Event):
    msg: str = ""


@pytest.mark.asyncio
async def test_publish_async() -> None:
    """异步发布触发处理器。"""
    bus = EventBus()
    got = []

    async def handler(e: Event) -> None:
        got.append(e.msg)  # type: ignore[attr-defined]

    bus.subscribe(Ping, handler)
    await bus.publish(Ping(msg="hi"))
    assert got == ["hi"]


def test_publish_sync() -> None:
    """同步发布跳过异步处理器。"""
    bus = EventBus()
    got = []
    bus.subscribe(Ping, lambda e: got.append(e.msg))  # type: ignore[attr-defined]
    bus.publish_sync(Ping(msg="x"))
    assert got == ["x"]


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    got = []

    async def handler(e: Event) -> None:
        got.append(e.msg)  # type: ignore[attr-defined]

    bus.subscribe(Ping, handler)
    bus.unsubscribe(Ping, handler)
    await bus.publish(Ping(msg="nope"))
    assert got == []


def test_clear_subscribers() -> None:
    bus = EventBus()
    bus.subscribe(Ping, lambda e: None)
    bus.clear()
    bus.publish_sync(Ping(msg="x"))
