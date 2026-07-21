from __future__ import annotations

import pytest

from echotools.base.errors import NoCandidateError
from echotools.exec.dispatch import TaskCandidate, TaskDispatcher, make_id
from echotools.exec.dispatch.selector import AdaptiveSelector


@pytest.mark.asyncio
async def test_dispatcher_single_candidate(tmp_path) -> None:
    async def executor(cand: TaskCandidate):
        yield "a"
        yield "b"

    dispatcher = TaskDispatcher(AdaptiveSelector(persist_dir=str(tmp_path)))
    chunks = []
    async for ch in dispatcher.dispatch(
        [TaskCandidate(id="only", group="g")],
        executor,
    ):
        chunks.append(ch)
    assert chunks == ["a", "b"]


@pytest.mark.asyncio
async def test_dispatcher_no_candidates_raises() -> None:
    dispatcher = TaskDispatcher()

    async def executor(c: TaskCandidate):
        yield "x"
        if False:
            yield

    with pytest.raises(NoCandidateError):
        async for _ in dispatcher.dispatch([], executor):
            pass


def test_make_id_random_suffix() -> None:
    a = make_id("grp")
    b = make_id("grp")
    assert a.startswith("grp_")
    assert a != b
