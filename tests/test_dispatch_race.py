from __future__ import annotations

from echotools import EchoTools
from echotools.dispatch import TaskCandidate, TaskDispatcher
from echotools.dispatch.selector import AdaptiveSelector


async def test_race_picks_first_to_min_tokens(tmp_path) -> None:
    async def executor(cand: TaskCandidate):
        count = int(cand.id.split("-")[-1])
        for i in range(count):
            yield f"tok-{i}"

    cands = [
        TaskCandidate(id="cand-3", group="g"),
        TaskCandidate(id="cand-10", group="g"),
    ]
    dispatcher = TaskDispatcher(AdaptiveSelector(persist_dir=str(tmp_path)))
    chunks = []
    async for ch in dispatcher.dispatch(cands, executor, concurrent=2, min_tokens=5):
        chunks.append(ch)

    assert len(chunks) >= 5
    assert all(isinstance(c, str) for c in chunks)


async def test_selector_flush_persists(tmp_path) -> None:
    selector = AdaptiveSelector(persist_dir=str(tmp_path), flush_debounce=0.01)
    await selector.record("cand-a", True, latency=0.1, tokens=3)
    await selector.flush()
    reloaded = AdaptiveSelector(persist_dir=str(tmp_path))
    stats = await reloaded.get_stats()
    assert "cand-a" in stats


async def test_selector_parallel_load(tmp_path) -> None:
    import json

    for i in range(55):
        path = tmp_path / f"cand-{i}.json"
        path.write_text(
            json.dumps({"group": "g", "n_success": 1, "n_fails": 0}),
            encoding="utf-8",
        )
    selector = AdaptiveSelector(persist_dir=str(tmp_path))
    stats = await selector.get_stats()
    assert len(stats) == 55


async def test_facade_startup_shutdown(tmp_path) -> None:
    et = EchoTools(service_name="test", persist_dir=str(tmp_path))
    et.logger.configure(level="DEBUG")
    await et.startup()
    await et.shutdown()
    assert "EchoTools" in repr(et)
