from __future__ import annotations

"""流式：``<entml:thinking>…</thinking>`` fault 容错 — ``FncallStreamParser`` 分片回归。"""

import json
from typing import Any, Dict, List

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import EntmlThinkingStreamFilter
from fixtures.simulated_fault_thinking_responses import (
    FaultThinkingCase,
    iter_fault_thinking_cases,
    tools_for_fault_case,
)

CASES = iter_fault_thinking_cases()
CASE_IDS = [c.id for c in CASES]
TOOL_CASES = [c for c in CASES if c.expect_names]
WORST_SPLIT_CASES = [c for c in CASES if c.worst_split]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _stream_parse(
    case: FaultThinkingCase,
    chunk_size: int,
) -> tuple[str, List[Dict[str, Any]], FncallStreamParser]:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_fault_case(case),
    )
    text = case.response
    for i in range(0, len(text), chunk_size):
        parser.feed(text[i : i + chunk_size])
    clean, calls = parser.finalize()
    return clean, calls, parser


def _assert_clean(case: FaultThinkingCase, clean: str, *, label: str) -> None:
    for needle in case.expect_clean_contains:
        assert needle in clean, f"{case.id}/{label}: clean missing {needle!r}"
    for bad in case.expect_clean_absent:
        assert bad not in clean, f"{case.id}/{label}: clean leaked {bad!r}"
    for bad in case.expect_clean_excludes:
        assert bad not in clean, f"{case.id}/{label}: clean must exclude {bad!r}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize("chunk_size", [1, 3, 5, 8, 17, 64], ids=lambda n: f"c{n}")
def test_stream_tool_calls(case: FaultThinkingCase, chunk_size: int) -> None:
    if chunk_size not in case.chunk_sizes:
        pytest.skip(f"chunk {chunk_size} not required for {case.id}")

    clean, calls, parser = _stream_parse(case, chunk_size)
    if case.expect_call_count is not None:
        assert len(calls) == case.expect_call_count, f"{case.id}/c{chunk_size}"
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), f"{case.id}/c{chunk_size}"
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), f"{case.id}/c{chunk_size}"
    _assert_clean(case, clean, label=f"c{chunk_size}")
    for needle in case.expect_thinking_contains:
        assert needle in parser.partial_thinking, (
            f"{case.id}/c{chunk_size}: thinking missing {needle!r}"
        )


@pytest.mark.parametrize("case", TOOL_CASES, ids=lambda c: c.id)
def test_stream_char_by_char(case: FaultThinkingCase) -> None:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_fault_case(case),
    )
    for ch in case.response:
        parser.feed(ch)
    _, calls = parser.finalize()
    assert _names(calls) == list(case.expect_names), case.id
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), case.id


@pytest.mark.parametrize("case", WORST_SPLIT_CASES, ids=lambda c: c.id)
def test_stream_split_at_angle_brackets(case: FaultThinkingCase) -> None:
    text = case.response
    tools = tools_for_fault_case(case)
    proto = get_protocol("entml")
    _, expect_calls = proto.parse(text, tools)

    cut_points = {0, len(text)}
    for i, ch in enumerate(text):
        if ch == "<":
            cut_points.update({max(0, i - 1), i, i + 1})

    for cut in sorted(cut_points):
        parser = FncallStreamParser(protocol=proto, tools=tools)
        if cut > 0:
            parser.feed(text[:cut])
        if cut < len(text):
            parser.feed(text[cut:])
        _, calls = parser.finalize()
        assert _names(calls) == _names(expect_calls), f"{case.id} cut={cut}"


@pytest.mark.parametrize("case", TOOL_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", [1, 8, 17], ids=lambda n: f"c{n}")
def test_stream_matches_batch_tools(case: FaultThinkingCase, chunk_size: int) -> None:
    if chunk_size not in case.chunk_sizes:
        pytest.skip(f"chunk {chunk_size} not required for {case.id}")
    _, batch_calls = get_protocol("entml").parse(case.response, tools_for_fault_case(case))
    _, stream_calls, _ = _stream_parse(case, chunk_size)
    assert _names(stream_calls) == _names(batch_calls), case.id
    assert _args(stream_calls) == _args(batch_calls), case.id


def test_stream_filter_fault_close_char_by_char() -> None:
    """EntmlThinkingStreamFilter：``</thinking>`` 逐字分片后仍能结束思考块。"""
    case = next(c for c in CASES if c.id == "model_fault_read_after_close")
    filt = EntmlThinkingStreamFilter()
    thinking_parts: List[str] = []
    for ch in case.response:
        for kind, piece in filt.feed(ch):
            if kind == "thinking":
                thinking_parts.append(piece)
    for kind, piece in filt.finalize():
        if kind == "thinking":
            thinking_parts.append(piece)
    joined = "".join(thinking_parts)
    assert "main.py" in joined
    assert not filt.in_open_thinking()


def test_stream_filter_waits_for_invoke_after_fault_close() -> None:
    filt = EntmlThinkingStreamFilter()
    filt.feed(
        "<entml:thinking>\n"
        "还在想...\n"
        "</thinking>\n"
        "中间说明，尚未出现 invoke\n"
    )
    assert filt.in_open_thinking()
