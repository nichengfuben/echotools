from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Union

import pytest

from echotools.dispatch import TaskCandidate, TaskDispatcher
from echotools.dispatch.selector import AdaptiveSelector


@pytest.mark.asyncio
async def test_single_dispatch(tmp_path) -> None:
    """单候选分发产出全部分片。"""
    selector = AdaptiveSelector(persist_dir=str(tmp_path))
    disp = TaskDispatcher(selector=selector)
    cand = TaskCandidate(id="c1", group="g")

    async def executor(
        c: TaskCandidate,
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        yield "a"
        yield "b"

    out = [x async for x in disp.dispatch([cand], executor)]
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_selector_record(tmp_path) -> None:
    """记录指标并持久化。"""
    sel = AdaptiveSelector(persist_dir=str(tmp_path))
    await sel.record("c1", True, latency=0.1, tokens=5, duration=1.0, group="g")
    stats = await sel.get_stats()
    assert "c1" in stats
    assert stats["c1"]["n_calls"] == 1
