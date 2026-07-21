from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, List
from unittest.mock import patch

import pytest

from echotools.version import get_version
from echotools.base.cache import ListCache, MemoryCache
from echotools.exec.dispatch import TaskCandidate, TaskDispatcher
from echotools.exec.dispatch.proxy_selector import ProxyRecord, ProxySelector
from echotools.exec.dispatch.selector import AdaptiveSelector, TASRecord
from echotools.exec.dispatch.usage import fallback_usage, normalize_usage
from echotools.base.errors.http import ForbiddenError, StreamError
from echotools.media.events import Event, EventBus
from echotools.base.io import atomic_write_text, read_text_if_exists
from echotools.exec.keys import KeyPool, KeyState
from echotools.exec.lifecycle import LifecycleManager
from echotools.base.logger.manager import LoggerManager, _LogFormatter, _supports_color
from echotools.base.retry import (
    retry_async_generator,
    retry_on_empty,
    retry_on_exception,
    retry_with_backoff,
)
from echotools.plat.scheduler import TaskScheduler
from echotools.media.tracing.context import (
    get_current_span_id,
    get_current_trace_id,
    get_request_id,
    reset_context,
    set_current_span_id,
    set_current_trace_id,
    set_request_id,
)
from echotools.media.tracing.span import Span, Trace
from echotools.media.tracing.tracer import Tracer
from echotools.media.web import stats as stats_mod
from echotools.media.web.broker import RequestBroker, request_broker
from echotools.media.web.stats import RequestStats


class _MockWS:
    def __init__(self, *, fail_json: bool = False, fail_str: bool = False) -> None:
        self.fail_json = fail_json
        self.fail_str = fail_str
        self.json_sent: List[Any] = []
        self.str_sent: List[str] = []

    async def send_json(self, data: Any) -> None:
        if self.fail_json:
            raise ConnectionError("json fail")
        self.json_sent.append(data)

    async def send_str(self, msg: str) -> None:
        if self.fail_str:
            raise ConnectionError("str fail")
        self.str_sent.append(msg)


@pytest.mark.asyncio
async def test_broker_register_history_and_broadcast() -> None:
    broker = RequestBroker()
    ws = _MockWS()
    await broker.register(ws)
    assert broker.has_listeners

    await broker.broadcast({"type": "request_start", "id": "r1", "path": "/x"})
    assert "r1" in broker._active

    await broker.broadcast({"type": "request_end", "id": "r1", "status": 200})
    assert broker.get_recent(5)

    count = await broker.send_history(ws)
    assert count >= 1

    await broker.unregister(ws)
    assert not broker.has_listeners


@pytest.mark.asyncio
async def test_broker_broadcast_stale_socket_removed() -> None:
    broker = RequestBroker()
    good = _MockWS()
    bad = _MockWS(fail_str=True)
    await broker.register(good)
    await broker.register(bad)
    await broker.broadcast({"type": "ping", "id": "1"})
    assert len(broker._sockets) == 1


def test_broker_push_event_with_loop() -> None:
    broker = RequestBroker()
    loop = asyncio.new_event_loop()
    broker.set_loop(loop)

    async def run() -> None:
        broker.set_loop(asyncio.get_running_loop())
        await broker.broadcast({"type": "request_end", "id": "p1", "status": 200})

    loop.run_until_complete(run())
    broker.push_event({"type": "request_end", "id": "p2", "status": 201})
    loop.close()


def test_request_stats_ring_buffer_and_snapshot() -> None:
    rb = stats_mod._RingBuffer(3)
    rb.append({"n": 1})
    rb.append({"n": 2})
    rb.append({"n": 3})
    rb.append({"n": 4})
    assert rb.count == 3
    snap = rb.snapshot()
    assert len(snap) == 3
    rb.clear()
    assert rb.count == 0

    stats = RequestStats()
    for i in range(5):
        stats.record(
            platform=f"p{i % 2}",
            model=f"m{i}",
            status=500 if i == 0 else 200,
            latency_ms=float(i + 1),
            tokens_in=i,
            tokens_out=i + 1,
        )
    full = stats.snapshot()
    assert full["total"] == 5
    assert full["errors"] == 1
    assert full["latency"]["p50"] > 0

    exported = stats.to_dict()
    restored = RequestStats()
    restored.restore(exported)
    assert restored.to_dict()["total"] == 5

    stats.reset()
    assert stats.snapshot()["total"] == 0


def test_request_stats_bucket_trim(monkeypatch) -> None:
    stats = RequestStats()
    base = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: base)
    for _ in range(stats._MAX_BUCKETS + 5):
        stats.record(status=200)
        base += stats._BUCKET_SECONDS
        monkeypatch.setattr(time, "time", lambda b=base: b)
    assert len(stats.to_dict()["time_buckets"]) <= stats._MAX_BUCKETS


def test_io_atomic_write_permission_retry(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    calls = {"n": 0}
    real_replace = os.replace

    def fake_replace(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] < 2:
            raise PermissionError("locked")
        real_replace(src, dst)

    with patch("echotools.base.io.io_utils.os.replace", side_effect=fake_replace):
        atomic_write_text(target, "data", retries=3)
    assert target.read_text(encoding="utf-8") == "data"


def test_io_atomic_write_fallback_and_read(tmp_path: Path) -> None:
    target = tmp_path / "fallback.txt"

    def always_fail(src: str, dst: str) -> None:
        raise PermissionError("locked")

    with patch("echotools.base.io.io_utils.os.replace", side_effect=always_fail):
        atomic_write_text(target, "fallback", retries=1)
    assert read_text_if_exists(target) == "fallback"


def test_logger_color_and_exception_formatting(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert _supports_color() is True

    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    assert _supports_color() is False

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert _supports_color() is True

    fmt = _LogFormatter("%m-%d %H:%M:%S", use_color=True)
    record = logging.LogRecord("m", logging.ERROR, "", 0, "boom", (), None)
    try:
        raise RuntimeError("x")
    except RuntimeError:
        record.exc_info = __import__("sys").exc_info()
    text = fmt.format(record)
    assert "boom" in text

    plain = _LogFormatter("%m-%d %H:%M:%S", use_color=False)
    assert "boom" in plain.format(record)

    mgr = LoggerManager()
    mgr.configure(level="INFO", color=True, log_file=None)
    mgr.set_color(False)


@pytest.mark.asyncio
async def test_retry_paths() -> None:
    async def fail_then_ok() -> str:
        if fail_then_ok.n < 1:  # type: ignore[attr-defined]
            fail_then_ok.n += 1  # type: ignore[attr-defined]
            raise ValueError("nope")
        return "ok"

    fail_then_ok.n = 0  # type: ignore[attr-defined]
    assert await retry_with_backoff(fail_then_ok, max_attempts=2, base_delay=0.001) == "ok"

    async def empty_dict() -> dict:
        return {"text": "   "}

    with pytest.raises(ValueError):
        await retry_on_empty(empty_dict, max_retries=1)

    async def none_resp() -> None:
        return None

    with pytest.raises(ValueError):
        await retry_on_empty(none_resp, max_retries=1)

    calls: List[int] = []

    def gen_factory():
        async def gen():
            if not calls:
                calls.append(1)
                raise OSError("stream fail")
            yield "chunk"

        return gen()

    out = []
    async for item in retry_async_generator(
        gen_factory,
        max_retries=1,
        base_delay=0.001,
        fatal_check=lambda e: isinstance(e, KeyboardInterrupt),
    ):
        out.append(item)
    assert out == ["chunk"]

    def fatal_factory():
        async def gen():
            raise KeyboardInterrupt()
            yield "x"  # pragma: no cover

        return gen()

    with pytest.raises(KeyboardInterrupt):
        async for _ in retry_async_generator(fatal_factory, max_retries=1):
            pass


@pytest.mark.asyncio
async def test_retry_on_exception_exhausted() -> None:
    async def always_fail() -> str:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await retry_on_exception(always_fail, max_retries=1)


def test_keys_cooldown_recovery(monkeypatch) -> None:
    ks = KeyState(key="k")
    now = 1000.0
    monkeypatch.setattr(time, "time", lambda: now)
    for _ in range(3):
        ks.mark_failure(cooldown=10.0)
    assert not ks.is_ready()
    now = 1011.0
    assert ks.is_ready()

    pool = KeyPool(["a", "b"])
    assert pool.get_best() is not None
    assert pool.get_available()


@pytest.mark.asyncio
async def test_list_cache_edge_cases(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    cache = ListCache("t", ["fb"], str(path))
    assert await cache.load() == ["fb"]

    cache2 = ListCache("t2", ["x"], str(tmp_path / "empty.json"))
    path2 = tmp_path / "empty.json"
    path2.write_text(json.dumps({"items": []}), encoding="utf-8")
    assert await cache2.load() == ["x"]

    cache3 = ListCache("t3", ["a"], str(tmp_path / "ow.json"), overwrite=True)

    async def empty_fetch() -> list:
        return []

    await cache3._do_refresh(empty_fetch, None)
    assert cache3.items == ["a"]

    cache4 = ListCache("t4", ["a"], str(tmp_path / "skip.json"))
    cache4._refreshing = True
    await cache4._do_refresh(empty_fetch, None)

    with patch.object(Path, "write_text", side_effect=OSError("disk full")):
        await cache4.save(["z"])


def test_memory_cache_move_to_end_on_update() -> None:
    c = MemoryCache(max_size=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("a", 3)
    c.set("c", 4)
    assert c.get("b") is None
    c.clear()
    assert c.get("a") is None


@pytest.mark.asyncio
async def test_dispatcher_race_and_failures(tmp_path: Path) -> None:
    sel = AdaptiveSelector(persist_dir=str(tmp_path))
    disp = TaskDispatcher(selector=sel)
    assert disp.selector is sel

    async def with_usage(c: TaskCandidate):
        for i in range(12):
            yield f"t{i}"
        yield {"usage": {"completion_tokens": 42}}

    cands = [
        TaskCandidate(id="slow-20", group="g"),
        TaskCandidate(id="fast-12", group="g"),
    ]
    chunks = []
    async for ch in disp.dispatch(cands, with_usage, concurrent=2, min_tokens=5):
        chunks.append(ch)
    assert len(chunks) >= 12

    async def bad(c: TaskCandidate):
        raise RuntimeError("boom")
        yield "x"  # pragma: no cover

    with pytest.raises(Exception):
        async for _ in disp.dispatch([TaskCandidate(id="x", group="g")], bad):
            pass

    async def all_fail(c: TaskCandidate):
        raise RuntimeError("fail")
        yield "x"  # pragma: no cover

    with pytest.raises(Exception):
        async for _ in disp.dispatch(
            [TaskCandidate(id="a", group="g"), TaskCandidate(id="b", group="g")],
            all_fail,
            concurrent=2,
        ):
            pass


@pytest.mark.asyncio
async def test_selector_cooling_and_scoring(tmp_path: Path) -> None:
    sel = AdaptiveSelector(persist_dir=str(tmp_path))
    await sel.record("c1", False, latency=0.1, group="g")
    await sel.record("c1", False, latency=0.1, group="g")
    await sel.record("c1", False, latency=0.1, group="g")

    cands = [
        TaskCandidate(id="c1", group="g"),
        TaskCandidate(id="c2", group="g"),
        TaskCandidate(id="c3", group="g"),
    ]
    picked = await sel.select(cands, count=2)
    assert picked

    rec = TASRecord(n_success=5, n_fails=1, latency_sum=100.0, latency_sum_sq=2000.0, n_latency_samples=2)
    score = sel._score(rec, time.time())
    assert score > 0

    await sel.record("c2", True, latency=50.0, tokens=10, duration=1.0, group="g")
    await sel.flush()


def test_proxy_selector_edge_cases(tmp_path: Path) -> None:
    rec = ProxyRecord()
    assert rec.success_rate == 0.5
    assert rec.mean_latency == 1000.0

    path = tmp_path / "proxy.json"
    path.write_text("{bad", encoding="utf-8")
    sel = ProxySelector(path)
    sel.record(use_proxy=True, success=True, latency_ms=10.0)
    sel.record(use_proxy=True, success=True, latency_ms=20.0)

    with patch("echotools.exec.dispatch.proxy_selector.atomic_write_text", side_effect=OSError("x")):
        sel.record(use_proxy=False, success=False)


def test_usage_normalize_branches() -> None:
    u = normalize_usage({"completion_tokens": 5}, prompt_len=30, resp_text="x")
    assert u["prompt_tokens"] >= 1
    u2 = normalize_usage({"prompt_tokens": 0, "completion_tokens": 0}, 30, "x")
    assert u2["total_tokens"] >= 1
    u3 = normalize_usage({"bad": "x"}, 30, "x")
    assert fallback_usage(30, "x")["total_tokens"] == u3["total_tokens"]


@pytest.mark.asyncio
async def test_event_bus_error_isolation() -> None:
    bus = EventBus()

    class Boom(Event):
        pass

    def bad_sync(_: Event) -> None:
        raise ValueError("sync")

    async def bad_async(_: Event) -> None:
        raise ValueError("async")

    bus.subscribe(Boom, bad_sync)
    bus.publish_sync(Boom())

    bus.subscribe(Boom, bad_async)
    await bus.publish(Boom())
    bus.unsubscribe(Boom, bad_sync)


@pytest.mark.asyncio
async def test_scheduler_failure_and_cancel() -> None:
    sched = TaskScheduler(max_concurrent=2)

    async def fail() -> None:
        raise ValueError("task fail")

    with pytest.raises(ValueError):
        await sched.submit("f", fail())

    async def slow() -> None:
        await asyncio.sleep(0.05)

    task = asyncio.create_task(sched.submit("s", slow()))
    await asyncio.sleep(0.01)
    await sched.cancel_all()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_tracing_context_and_span_api() -> None:
    reset_context()
    set_current_trace_id("t1")
    set_current_span_id("s1")
    set_request_id("r1")
    assert get_current_span_id() == "s1"
    assert get_request_id() == "r1"
    reset_context()
    assert get_current_trace_id() is None

    span = Span("x", "trace")
    span.set_tag("k", 1).log("msg", extra=1)
    span.finish()
    span.finish()
    d = span.to_dict()
    assert d["name"] == "x"

    trace = Trace("custom")
    child = trace.start_span("child")
    trace.finish_span(child)
    assert trace.to_dict()["trace_id"] == "custom"

    finished: List[str] = []
    tracer = Tracer(on_finish=lambda t: finished.append(t.trace_id))
    with tracer.trace("root") as tr:
        with tracer.span(tr, "inner"):
            pass
    assert finished


def test_http_errors_and_version() -> None:
    assert ForbiddenError().status_code == 403
    assert StreamError().status_code == 502
    assert get_version()


@pytest.mark.asyncio
async def test_lifecycle_shutdown_hook_error() -> None:
    lm = LifecycleManager()
    lm.on_startup(lambda: None)

    async def bad_shutdown() -> None:
        raise RuntimeError("shutdown fail")

    lm.on_shutdown(bad_shutdown)
    await lm.startup()
    await lm.shutdown()
    assert not lm.started


def test_request_broker_singleton() -> None:
    assert isinstance(request_broker, RequestBroker)
