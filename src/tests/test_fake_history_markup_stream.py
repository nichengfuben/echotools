from __future__ import annotations

"""流式：伪 history 标签模拟模型回复 — ``FncallStreamParser`` / ``partial_text`` 回归。"""

import json
from typing import Any, Dict, List, Optional

import pytest
from fixtures.simulated_fake_history_markup_responses import (
    HistoryMarkupCase,
    iter_fake_history_markup_cases,
    tools_for_markup_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser

CASES = iter_fake_history_markup_cases()
CASE_IDS = [c.id for c in CASES]
PARTIAL_CASES = [c for c in CASES if c.check_partial_text]
WORST_SPLIT_CASES = [c for c in CASES if c.worst_split]
INVOKE_CASES = [c for c in CASES if c.expect_names]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _protocol_options(case: HistoryMarkupCase) -> Optional[Dict[str, Any]]:
    if case.thinking_mode is None:
        return None
    return {"thinking_mode": case.thinking_mode}


def _stream_parse(
    case: HistoryMarkupCase,
    chunk_size: int,
) -> tuple[str, List[Dict[str, Any]], FncallStreamParser]:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_markup_case(case),
        protocol_options=_protocol_options(case),
    )
    text = case.response
    for i in range(0, len(text), chunk_size):
        parser.feed(text[i : i + chunk_size])
    clean, calls = parser.finalize()
    return clean, calls, parser


def _assert_clean(case: HistoryMarkupCase, clean: str, *, label: str) -> None:
    for needle in case.expect_clean_contains:
        assert needle in clean, f"{case.id}/{label}: clean missing {needle!r}"
    for bad in case.expect_clean_absent:
        assert bad not in clean, f"{case.id}/{label}: clean leaked {bad!r}"
    for bad in case.expect_clean_excludes:
        assert bad not in clean, f"{case.id}/{label}: clean must exclude {bad!r}"


def _assert_no_partial_leak(case: HistoryMarkupCase, partial: str, *, label: str) -> None:
    for marker in case.partial_leak_markers:
        assert marker not in partial, (
            f"{case.id}/{label}: partial_text leaked {marker!r}"
        )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize("chunk_size", [1, 3, 5, 8, 17, 64], ids=lambda n: f"c{n}")
def test_stream_finalize(case: HistoryMarkupCase, chunk_size: int) -> None:
    if chunk_size not in case.chunk_sizes:
        pytest.skip(f"chunk {chunk_size} not required for {case.id}")

    clean, calls, _ = _stream_parse(case, chunk_size)
    assert len(calls) == case.expect_call_count, f"{case.id}/c{chunk_size}"
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), f"{case.id}/c{chunk_size}"
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), f"{case.id}/c{chunk_size}"
    _assert_clean(case, clean, label=f"c{chunk_size}")


@pytest.mark.parametrize("case", PARTIAL_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", [1, 4, 8, 17, 64], ids=lambda n: f"c{n}")
def test_stream_partial_text_no_leak(case: HistoryMarkupCase, chunk_size: int) -> None:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_markup_case(case),
        protocol_options=_protocol_options(case),
    )
    text = case.response
    for i in range(0, len(text), chunk_size):
        parser.feed(text[i : i + chunk_size])
        _assert_no_partial_leak(case, parser.partial_text, label=f"c{chunk_size}@{i}")
    clean, calls = parser.finalize()
    assert len(calls) == case.expect_call_count
    _assert_clean(case, clean, label=f"partial_c{chunk_size}")


@pytest.mark.parametrize("case", PARTIAL_CASES, ids=lambda c: c.id)
def test_stream_char_by_char_partial(case: HistoryMarkupCase) -> None:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_markup_case(case),
        protocol_options=_protocol_options(case),
    )
    for ch in case.response:
        parser.feed(ch)
        _assert_no_partial_leak(case, parser.partial_text, label="char")
    clean, calls = parser.finalize()
    assert len(calls) == case.expect_call_count, case.id
    _assert_clean(case, clean, label="char")


@pytest.mark.parametrize("case", INVOKE_CASES, ids=lambda c: c.id)
def test_stream_char_by_char_invoke(case: HistoryMarkupCase) -> None:
    clean, calls, _ = _stream_parse(case, 1)
    assert _names(calls) == list(case.expect_names), case.id
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), case.id
    _assert_clean(case, clean, label="char_invoke")


@pytest.mark.parametrize("case", WORST_SPLIT_CASES, ids=lambda c: c.id)
def test_stream_split_at_angle_brackets(case: HistoryMarkupCase) -> None:
    text = case.response
    tools = tools_for_markup_case(case)
    proto = get_protocol("entml")
    _, expect_calls = proto.parse(text, tools)

    cut_points = {0, len(text)}
    for i, ch in enumerate(text):
        if ch == "<":
            cut_points.add(i)
        if ch == "\n":
            cut_points.add(i)

    for cut in sorted(cut_points):
        if cut <= 0 or cut >= len(text):
            continue
        parser = FncallStreamParser(protocol=proto, tools=tools)
        parser.feed(text[:cut])
        parser.feed(text[cut:])
        clean, calls = parser.finalize()
        assert len(calls) == len(expect_calls), f"{case.id} cut@{cut}"
        if expect_calls:
            assert _names(calls) == _names(expect_calls), f"{case.id} cut@{cut}"
        _assert_clean(case, clean, label=f"cut@{cut}")
