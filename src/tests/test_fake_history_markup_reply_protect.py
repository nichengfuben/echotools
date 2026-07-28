from __future__ import annotations

"""batch parse 与 stream finalize 对 invoke / 可见回复的保护须一致。"""

import json
from typing import Any, Dict, List

import pytest
from fixtures.simulated_fake_history_markup_responses import (
    REAL_READ_INVOKE,
    REAL_WEATHER_INVOKE,
    HistoryMarkupCase,
    iter_fake_history_markup_cases,
    tools_for_markup_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.shared.history_markup import strip_fake_history_markup

INVOKE_REPLY_CASES = [
    c
    for c in iter_fake_history_markup_cases()
    if c.expect_names
    or c.id
    in (
        "unclosed_fake_tool_invoke_trailing_reply",
        "function_calls_wrap_trailing_reply",
        "invoke_then_fake_tool_then_reply",
        "fake_tool_inside_function_calls_with_invoke",
    )
]

EXTRA_CASES = (
    HistoryMarkupCase(
        id="visible_reply_before_and_after_invoke",
        description="invoke 前后均有可见说明",
        extra_tools=("Read",),
        response=(
            "开头说明。\n"
            f"{REAL_READ_INVOKE}\n"
            "结尾说明。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("开头说明", "结尾说明"),
        expect_clean_excludes=("<tool>",),
        partial_leak_markers=("{Edit:", "\n<tool>\n"),
    ),
    HistoryMarkupCase(
        id="thinking_visible_fake_invoke_reply",
        description="thinking + 可见区伪块 + invoke + 尾句",
        extra_tools=("Read", "Edit"),
        response=(
            "<entml:thinking>\nplan\n</entml:thinking>\n"
            "中间说明\n"
            "<tool>\n{Edit: x}\n</tool>\n"
            f"{REAL_READ_INVOKE}\n"
            "最终回复"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("中间说明", "最终回复"),
        expect_clean_excludes=("Edit", "<tool>"),
    ),
    HistoryMarkupCase(
        id="weather_after_unclosed_fake_tool",
        description="未闭合伪 tool 后直接 weather invoke + 尾句",
        response=(
            "参考\n<tool>\n{get_weather: x}\n"
            f"{REAL_WEATHER_INVOKE}\n"
            "确认完毕。"
        ),
        expect_names=("get_weather",),
        expect_args=({"city": "杭州", "unit": "c"},),
        expect_call_count=1,
        expect_clean_contains=("参考", "确认完毕"),
        expect_clean_excludes=("{get_weather:", "<tool>"),
        worst_split=True,
    ),
)

ALL_CASES = INVOKE_REPLY_CASES + list(EXTRA_CASES)


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _batch(case: HistoryMarkupCase) -> tuple[str, List[Dict[str, Any]]]:
    return get_protocol("entml").parse(case.response, tools_for_markup_case(case))


def _stream(case: HistoryMarkupCase, chunk: int) -> tuple[str, List[Dict[str, Any]]]:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_markup_case(case),
    )
    text = case.response
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    return parser.finalize()


def _assert_case(case: HistoryMarkupCase, clean: str, calls: List[Dict[str, Any]], label: str) -> None:
    assert len(calls) == case.expect_call_count, f"{case.id}/{label}: call count"
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), f"{case.id}/{label}: names"
    if case.expect_args:
        assert _args(calls) == list(case.expect_args), f"{case.id}/{label}: args"
    for needle in case.expect_clean_contains:
        assert needle in clean, f"{case.id}/{label}: missing {needle!r}"
    for bad in case.expect_clean_excludes:
        assert bad not in clean, f"{case.id}/{label}: leaked {bad!r}"
    assert "entml:invoke" not in clean, f"{case.id}/{label}: invoke tag in clean"


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
def test_batch_stream_parity(case: HistoryMarkupCase) -> None:
    batch_clean, batch_calls = _batch(case)
    stream_clean, stream_calls = _stream(case, 3)
    _assert_case(case, batch_clean, batch_calls, "batch")
    _assert_case(case, stream_clean, stream_calls, "stream")
    for needle in case.expect_clean_contains:
        assert needle in batch_clean and needle in stream_clean, case.id


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk", [1, 8, 17, 64], ids=lambda n: f"c{n}")
def test_stream_chunk_sizes(case: HistoryMarkupCase, chunk: int) -> None:
    clean, calls = _stream(case, chunk)
    _assert_case(case, clean, calls, f"c{chunk}")


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
def test_strip_preserves_invoke_and_reply(case: HistoryMarkupCase) -> None:
    if not case.expect_names:
        return
    if "<entml:invoke" not in case.response:
        return
    stripped, _ = strip_fake_history_markup(case.response)
    assert "entml:invoke" in stripped, case.id
    for needle in case.expect_clean_contains:
        if needle not in ("说明", "参考历史", "我再确认一次"):
            assert needle in stripped or needle in case.response, case.id


def test_function_calls_partial_display() -> None:
    partial = (
        "说明。\n<tool>\n{Edit: x}\n"
        "<entml:function_calls>\n"
        '<entml:invoke name="Read">\n'
        '<entml:parameter name="path">a.py'
    )
    from echotools.exec.fncall.shared.history_markup import (
        strip_fake_history_markup_for_display,
    )

    display, _ = strip_fake_history_markup_for_display(partial)
    assert "说明" in display
    assert "<entml:invoke" in display
    assert "entml:parameter" not in display or "<entml:invoke" in display
