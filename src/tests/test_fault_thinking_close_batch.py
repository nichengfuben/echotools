from __future__ import annotations

"""非流式：``<entml:thinking>…</thinking>`` fault 容错 — ``protocol.parse`` / ``split_entml_thinking``。"""

import json
from typing import Any, Dict, List

import pytest
from fixtures.simulated_fault_thinking_responses import (
    FaultThinkingCase,
    iter_fault_thinking_cases,
    tools_for_fault_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.protocols.entml_think.parse import (
    find_complete_entml_invoke_open,
    has_unclosed_entml_thinking,
    invoke_index_inside_unclosed_thinking,
    split_entml_thinking,
)

CASES = iter_fault_thinking_cases()
CASE_IDS = [c.id for c in CASES]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _batch_parse(case: FaultThinkingCase) -> tuple[str, List[Dict[str, Any]]]:
    return get_protocol("entml").parse(case.response, tools_for_fault_case(case))


def _clean_needles(case: FaultThinkingCase) -> tuple[str, ...]:
    return case.expect_clean_contains


def _assert_clean(case: FaultThinkingCase, clean: str, *, label: str) -> None:
    for needle in _clean_needles(case):
        assert needle in clean, f"{case.id}/{label}: clean missing {needle!r}"
    for bad in case.expect_clean_absent:
        assert bad not in clean, f"{case.id}/{label}: clean leaked {bad!r}"
    for bad in case.expect_clean_excludes:
        assert bad not in clean, f"{case.id}/{label}: clean must exclude {bad!r}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_batch_tool_calls(case: FaultThinkingCase) -> None:
    clean, calls = _batch_parse(case)
    if case.expect_call_count is not None:
        assert len(calls) == case.expect_call_count, case.id
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), case.id
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), case.id
    _assert_clean(case, clean, label="batch")


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_batch_split_entml_thinking(case: FaultThinkingCase) -> None:
    content, thinking = split_entml_thinking(case.response)
    if case.expect_split_thinking_empty:
        assert thinking == "", case.id
        assert has_unclosed_entml_thinking(case.response), case.id
        return
    for needle in case.expect_split_thinking_contains:
        assert needle in thinking, f"{case.id}: split missing {needle!r}"
    if case.expect_names:
        assert not has_unclosed_entml_thinking(case.response), case.id
        assert not has_unclosed_entml_thinking(content), case.id


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_batch_invoke_not_inside_unclosed_thinking(case: FaultThinkingCase) -> None:
    pos = find_complete_entml_invoke_open(case.response)
    if case.expect_names:
        assert pos >= 0, case.id
        assert not invoke_index_inside_unclosed_thinking(case.response, pos), case.id
    elif case.id == "model_invoke_inside_before_fault_close":
        assert pos >= 0, case.id
        assert invoke_index_inside_unclosed_thinking(case.response, pos), case.id
