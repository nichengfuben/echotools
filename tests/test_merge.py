from __future__ import annotations

from echotools.config.merge import merge_dicts
from echotools.dispatch import TaskCandidate, make_id


def test_merge_dicts_nested() -> None:
    target = {"a": {"x": 1}}
    source = {"a": {"y": 2}, "b": 3}
    merge_dicts(target, source)
    assert target["a"]["x"] == 1
    assert target["a"]["y"] == 2
    assert target["b"] == 3


def test_make_id_deterministic() -> None:
    a = make_id("g", "res")
    b = make_id("g", "res")
    assert a == b
    assert a.startswith("g_")


def test_task_candidate_capability() -> None:
    cand = TaskCandidate(id="1", group="g", capabilities={"stream": True})
    assert cand.has_capability("stream")
    assert not cand.has_capability("missing")
