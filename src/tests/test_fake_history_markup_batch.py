from __future__ import annotations

"""非流式：伪 history 标签模拟模型回复 — ``protocol.parse`` 回归。"""

import json
from typing import Any, Dict, List

import pytest
from fixtures.simulated_fake_history_markup_responses import (
    HistoryMarkupCase,
    iter_fake_history_markup_cases,
    tools_for_markup_case,
)

from echotools.exec.fncall import get_protocol

CASES = iter_fake_history_markup_cases()
CASE_IDS = [c.id for c in CASES]
INVOKE_CASES = [c for c in CASES if c.expect_names]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _batch_parse(case: HistoryMarkupCase) -> tuple[str, List[Dict[str, Any]]]:
    return get_protocol("entml").parse(case.response, tools_for_markup_case(case))


def _assert_clean(case: HistoryMarkupCase, clean: str, *, label: str) -> None:
    for needle in case.expect_clean_contains:
        assert needle in clean, f"{case.id}/{label}: clean missing {needle!r}"
    for bad in case.expect_clean_absent:
        assert bad not in clean, f"{case.id}/{label}: clean leaked {bad!r}"
    for bad in case.expect_clean_excludes:
        assert bad not in clean, f"{case.id}/{label}: clean must exclude {bad!r}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_batch_no_fake_markup_leak(case: HistoryMarkupCase) -> None:
    clean, calls = _batch_parse(case)
    assert len(calls) == case.expect_call_count, case.id
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), case.id
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), case.id
    _assert_clean(case, clean, label="batch")


@pytest.mark.parametrize("case", INVOKE_CASES, ids=lambda c: c.id)
def test_batch_fake_block_not_duplicated_with_invoke(case: HistoryMarkupCase) -> None:
    """全文含 entml invoke 时，伪 ``<tool>`` 块不得额外产生 tool_calls。"""
    clean, calls = _batch_parse(case)
    assert len(calls) == case.expect_call_count, case.id
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), case.id


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_strip_unit_matches_batch(case: HistoryMarkupCase) -> None:
    from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup

    stripped, _ = strip_fake_history_markup(case.response)
    for bad in case.expect_clean_excludes:
        if bad in ("Edit", "ghost", "secret.py", "485                       buf", "{Read:", "{Edit:", "{Bash:", "{Write:", "{get_weather:"):
            assert bad not in stripped, f"{case.id}: strip still has {bad!r}"
