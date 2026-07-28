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
def test_batch_fake_block_not_parsed_as_tool(case: HistoryMarkupCase) -> None:
    """伪 history 块前的 brace 行不得被 parse 成 tool_calls。"""
    proto = get_protocol("entml")
    tools = tools_for_markup_case(case)
    split_at = case.response.find("<entml:invoke")
    prefix = case.response if split_at < 0 else case.response[:split_at]
    pre, pre_calls = proto.parse(prefix, tools)
    assert not pre_calls, case.id
    for bad in case.expect_clean_excludes:
        if bad.startswith("{") or bad in ("Edit", "ghost", "secret.py"):
            assert bad not in pre, f"{case.id}: prefix leaked {bad!r}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_strip_unit_matches_batch(case: HistoryMarkupCase) -> None:
    from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup

    stripped, _ = strip_fake_history_markup(case.response)
    for bad in case.expect_clean_excludes:
        if bad in ("Edit", "ghost", "secret.py", "485                       buf", "{Read:", "{Edit:", "{Bash:", "{Write:", "{get_weather:"):
            assert bad not in stripped, f"{case.id}: strip still has {bad!r}"
