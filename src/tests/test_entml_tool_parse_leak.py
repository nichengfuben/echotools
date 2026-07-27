from __future__ import annotations

import json

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking

WEATHER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "unit": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["city"],
            },
        },
    }
]

SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "filters": {"type": "object"},
                },
                "required": ["query"],
            },
        },
    }
]


def _args(calls):
    return [json.loads(c["function"]["arguments"]) for c in calls]


@pytest.mark.parametrize(
    "sample,expected_args",
    [
        (
            (
                "先查天气。\n"
                "<entml:function_calls>\n"
                '<entml:invoke name="get_weather">\n'
                '<entml:parameter name="city">杭州</entml:parameter>\n'
                "</entml:invoke>\n"
                "</entml:function_calls>"
            ),
            [{"city": "杭州"}],
        ),
        (
            (
                '<entml:invoke name="get_weather">\n'
                '<entml:parameter type="str" name="city">杭州</entml:parameter>\n'
                "</entml:invoke>"
            ),
            [{"city": "杭州"}],
        ),
        (
            (
                '<entml:invoke name="get_weather" id="1">\n'
                '<entml:parameter name="city">杭州</entml:parameter>\n'
                "</entml:invoke>"
            ),
            [{"city": "杭州"}],
        ),
        (
            (
                "<entml:invoke name='get_weather'>\n"
                "<entml:parameter name='city'>杭州</entml:parameter>\n"
                "</entml:invoke>"
            ),
            [{"city": "杭州"}],
        ),
        (
            (
                '<entml:invoke name="get\\_weather">\n'
                '<entml:parameter name="city">杭州</entml:parameter>\n'
                "</entml:invoke>"
            ),
            [{"city": "杭州"}],
        ),
        (
            (
                '<entml:invoke name="get_weather">\n'
                '<entml:parameter name="city">杭州</entml:parameter>\n'
                '<entml:parameter name="unit">c</entml:parameter>\n'
                '<entml:parameter name="limit">3</entml:parameter>\n'
                "</entml:invoke>"
            ),
            [{"city": "杭州", "unit": "c", "limit": 3}],
        ),
    ],
)
def test_entml_parse_variants_no_tag_leak(sample: str, expected_args: list) -> None:
    proto = get_protocol("entml")
    clean, calls = proto.parse(sample, WEATHER_TOOLS)
    assert calls
    assert calls[0]["function"]["name"] == "get_weather"
    assert _args(calls) == expected_args
    assert "entml:" not in clean
    assert "<entml" not in clean
    assert "</entml" not in clean


def test_entml_parse_preserves_thinking_for_split() -> None:
    proto = get_protocol("entml")
    text = (
        "<entml:thinking>plan the call</entml:thinking>\n"
        "好的。\n"
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">杭州</entml:parameter>'
        "</entml:invoke>"
    )
    clean, calls = proto.parse(text, WEATHER_TOOLS)
    assert _args(calls) == [{"city": "杭州"}]
    assert "<entml:thinking>" in clean
    display, thinking = split_entml_thinking(clean)
    assert thinking == "plan the call"
    assert "entml:" not in display
    assert "好的。" in display


def test_entml_parse_complex_parameters() -> None:
    proto = get_protocol("entml")
    text = (
        '<entml:invoke name="search">\n'
        '<entml:parameter name="query">q</entml:parameter>\n'
        '<entml:parameter name="tags">["a", "b"]</entml:parameter>\n'
        '<entml:parameter name="filters">{"lang": "zh"}</entml:parameter>\n'
        '<entml:parameter name="limit">2</entml:parameter>\n'
        "</entml:invoke>"
    )
    clean, calls = proto.parse(text, SEARCH_TOOLS)
    assert clean == ""
    assert _args(calls) == [
        {"query": "q", "tags": ["a", "b"], "filters": {"lang": "zh"}, "limit": 2}
    ]


def test_entml_parse_parameters_json_block() -> None:
    proto = get_protocol("entml")
    text = (
        '<entml:invoke name="search">'
        '<entml:parameters>{"query":"q","limit":2,"tags":["x"]}</entml:parameters>'
        "</entml:invoke>"
    )
    _, calls = proto.parse(text, SEARCH_TOOLS)
    assert _args(calls) == [{"query": "q", "limit": 2, "tags": ["x"]}]


def test_entml_orphan_tool_tags_stripped_without_calls() -> None:
    proto = get_protocol("entml")
    text = '结果：</entml:invoke><entml:parameter name="x">y</entml:parameter>'
    clean, calls = proto.parse(text, WEATHER_TOOLS)
    assert calls == []
    assert "entml:" not in clean
    assert "结果：" in clean


def test_entml_markdown_fence_residue_cleaned() -> None:
    proto = get_protocol("entml")
    text = (
        "```xml\n"
        '<entml:invoke name="get_weather">\n'
        '<entml:parameter name="city">杭州</entml:parameter>\n'
        "</entml:invoke>\n"
        "```"
    )
    clean, calls = proto.parse(text, WEATHER_TOOLS)
    assert _args(calls) == [{"city": "杭州"}]
    assert "entml:" not in clean
    assert "```" not in clean


def test_entml_stream_function_calls_wrapper_no_leak() -> None:
    proto = get_protocol("entml")
    text = (
        "查询中\n"
        "<entml:function_calls>\n"
        '<entml:invoke name="search">\n'
        '<entml:parameter name="query">hello</entml:parameter>\n'
        '<entml:parameter name="limit">5</entml:parameter>\n'
        "</entml:invoke>\n"
        "</entml:function_calls>"
    )
    parser = FncallStreamParser(protocol=proto, tools=SEARCH_TOOLS)
    for i in range(0, len(text), 5):
        parser.feed(text[i : i + 5])
    clean, calls = parser.finalize()
    assert _args(calls) == [{"query": "hello", "limit": 5}]
    assert "entml:" not in clean
    assert clean == "查询中"


def test_entml_stream_incremental_invoke_params() -> None:
    proto = get_protocol("entml")
    chunks = [
        "先说一句。",
        '<entml:invoke name="get_weather">',
        '<entml:parameter type="str" name="city">',
        "上海",
        "</entml:parameter>",
        '<entml:parameter name="limit" type="int">',
        "4",
        "</entml:parameter>",
        "</entml:invoke>",
    ]
    parser = FncallStreamParser(protocol=proto, tools=WEATHER_TOOLS)
    for chunk in chunks:
        parser.feed(chunk)
    clean, calls = parser.finalize()
    assert clean == "先说一句。"
    assert _args(calls) == [{"city": "上海", "limit": 4}]


def test_entml_stream_ready_tool_calls_incremental() -> None:
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=WEATHER_TOOLS)
    assert parser.feed("hi ") == []
    ready = parser.feed(
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">A</entml:parameter>'
        "</entml:invoke>"
    )
    assert len(ready) == 1
    assert json.loads(ready[0]["function"]["arguments"]) == {"city": "A"}
    ready2 = parser.feed(
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">B</entml:parameter>'
        "</entml:invoke>"
    )
    assert len(ready2) == 1
    assert json.loads(ready2[0]["function"]["arguments"]) == {"city": "B"}
    # 已由 feed 增量返回过的不应再出现
    assert parser.get_ready_tool_calls() == []
    clean, all_calls = parser.finalize()
    assert clean == "hi"
    assert len(all_calls) == 2
