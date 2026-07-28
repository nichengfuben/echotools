from __future__ import annotations

"""``entml:invoke`` 保护区：伪 history 剥离不得误伤真实工具调用。"""

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
from echotools.exec.fncall.shared.history_markup import (
    strip_fake_history_markup,
    strip_fake_history_markup_for_display,
)

READ_TOOL = {
    "type": "function",
    "function": {
        "name": "Read",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}

INVOKE_CASES = [
    c
    for c in iter_fake_history_markup_cases()
    if c.expect_names or "invoke" in c.id
]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


@pytest.mark.parametrize("case", INVOKE_CASES, ids=lambda c: c.id)
def test_batch_preserves_entml_invoke(case: HistoryMarkupCase) -> None:
    clean, calls = get_protocol("entml").parse(
        case.response, tools_for_markup_case(case)
    )
    assert len(calls) == case.expect_call_count, case.id
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), case.id
    assert "entml:invoke" not in clean, case.id


@pytest.mark.parametrize("case", INVOKE_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk", [1, 3, 8, 17], ids=lambda n: f"c{n}")
def test_stream_preserves_entml_invoke(case: HistoryMarkupCase, chunk: int) -> None:
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=tools_for_markup_case(case),
    )
    text = case.response
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
        if case.expect_names:
            assert "entml:parameter" not in parser.partial_text, case.id
    clean, calls = parser.finalize()
    assert len(calls) == case.expect_call_count, f"{case.id}/c{chunk}"
    if case.expect_names:
        assert _names(calls) == list(case.expect_names), f"{case.id}/c{chunk}"
    assert "entml:invoke" not in clean, f"{case.id}/c{chunk}"


def test_strip_never_removes_entml_invoke_block() -> None:
    text = (
        "说明。\n<tool>\n{Edit: x}\n"
        f"{REAL_READ_INVOKE}\n"
        "</tool>\n"
    )
    stripped, _ = strip_fake_history_markup(text)
    assert REAL_READ_INVOKE in stripped
    assert "entml:invoke" in stripped
    assert "{Edit:" not in stripped


def test_display_preserves_partial_entml_invoke() -> None:
    partial = f"说明。\n<tool>\n{{Edit: x}}\n{REAL_READ_INVOKE[:40]}"
    display, _ = strip_fake_history_markup_for_display(partial)
    assert "<entml:invoke" in display
    assert "entml:parameter" not in display or "<entml:invoke" in display


def test_unclosed_fake_stream_char_by_char_still_parses_read() -> None:
    text = (
        "说明。\n<tool>\n{Edit: x}\n"
        f"{REAL_READ_INVOKE}"
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
    for ch in text:
        parser.feed(ch)
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "Read"
    assert "Edit" not in clean


def test_weather_invoke_after_history_fake_block() -> None:
    text = (
        "参考\n<tool>\n{get_weather: x}\n</tool>\n"
        f"{REAL_WEATHER_INVOKE}"
    )
    clean, calls = get_protocol("entml").parse(text, tools_for_markup_case(
        HistoryMarkupCase(
            id="_",
            description="_",
            response=text,
            expect_names=("get_weather",),
            expect_call_count=1,
        )
    ))
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert "entml:invoke" not in clean
