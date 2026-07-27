from __future__ import annotations

"""entml 流式/批量解析器全方位测试：普通路径 + 边界 + rogator/Claude Code 高发场景。

与 test_simulated_llm_tool_parse / test_adversarial_stream_splits 互补：
- 本文件聚焦 thinking/invoke 边界、fault ``</thinking>``、holdback 分片、
  增量 API（ready/delta）、截断流、错误格式等。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking

# ---------------------------------------------------------------------------
# 工具 schema
# ---------------------------------------------------------------------------

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "unit": {"type": "string"},
            },
            "required": ["city"],
        },
    },
}

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

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}

STANDARD_TOOLS = [WEATHER_TOOL, READ_TOOL, SEARCH_TOOL]

READ_PATH = "C:/Users/Administrator/cursor_agent_simple.py"

READ_INVOKE = (
    '<entml:invoke name="Read">\n'
    f'<entml:parameter name="path">{READ_PATH}</entml:parameter>\n'
    "</entml:invoke>"
)

WEATHER_INVOKE = (
    '<entml:invoke name="get_weather">\n'
    '<entml:parameter name="city">杭州</entml:parameter>\n'
    '<entml:parameter name="unit">c</entml:parameter>\n'
    "</entml:invoke>"
)

CHUNK_SIZES = [1, 3, 7, 8, 17, 64]
FAULT_CLOSE_CHUNKS = [1, 5, 8, 17, 23]


@dataclass(frozen=True)
class ParserScenario:
    id: str
    text: str
    tools: Sequence[Dict[str, Any]] = field(default_factory=lambda: list(STANDARD_TOOLS))
    expect_names: Tuple[str, ...] = ()
    expect_args: Tuple[Dict[str, Any], ...] = ()
    expect_call_count: Optional[int] = None
    expect_thinking_contains: Tuple[str, ...] = ()
    expect_thinking_excludes: Tuple[str, ...] = ()
    expect_clean_contains: Tuple[str, ...] = ()
    expect_clean_excludes: Tuple[str, ...] = field(
        default_factory=lambda: ("entml:invoke", "entml:parameter")
    )
    expect_json_delta_valid: Optional[bool] = None
    chunk_sizes: Tuple[int, ...] = field(default_factory=lambda: CHUNK_SIZES)
    split_at_angle_brackets: bool = False
    # 批量 parse() 不过滤 thinking 内 invoke，与流式不一致时设为 True
    stream_only: bool = False


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _stream_parse(
    text: str,
    tools: Sequence[Dict[str, Any]],
    chunk_size: int,
) -> Tuple[str, List[Dict[str, Any]], FncallStreamParser]:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=list(tools))
    if chunk_size <= 0:
        parser.feed(text)
    else:
        for i in range(0, len(text), chunk_size):
            parser.feed(text[i : i + chunk_size])
    clean, calls = parser.finalize()
    return clean, calls, parser


def _collect_json_deltas(text: str, chunk_size: int) -> str:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=list(STANDARD_TOOLS))
    parts: List[str] = []
    for i in range(0, len(text), chunk_size):
        parser.feed(text[i : i + chunk_size])
        delta = parser.consume_stream_delta()
        if delta:
            parts.append(delta[1])
    parser.finalize()
    return "".join(parts)


def _assert_scenario(
    scenario: ParserScenario,
    clean: str,
    calls: List[Dict[str, Any]],
    parser: FncallStreamParser,
    *,
    label: str,
) -> None:
    sid = scenario.id
    if scenario.expect_call_count is not None:
        assert len(calls) == scenario.expect_call_count, f"{sid}/{label}: call count"
    if scenario.expect_names:
        assert _names(calls) == list(scenario.expect_names), f"{sid}/{label}: names"
    if scenario.expect_args:
        assert _args(calls) == list(scenario.expect_args), f"{sid}/{label}: args"

    display, thinking_from_clean = split_entml_thinking(clean)
    thinking = (parser.partial_thinking + "\n" + thinking_from_clean).strip()

    for needle in scenario.expect_thinking_contains:
        assert needle in thinking, f"{sid}/{label}: thinking missing {needle!r}"

    for banned in scenario.expect_thinking_excludes:
        assert banned not in thinking, f"{sid}/{label}: thinking leaked {banned!r}"

    for needle in scenario.expect_clean_contains:
        assert needle in display or needle in clean, f"{sid}/{label}: clean missing {needle!r}"

    for banned in scenario.expect_clean_excludes:
        assert banned not in display, f"{sid}/{label}: clean leaked {banned!r}"


# ---------------------------------------------------------------------------
# 语料
# ---------------------------------------------------------------------------

def _scenarios() -> List[ParserScenario]:
    example_in_thinking = (
        "<entml:thinking>\n"
        "格式示例：\n"
        '<entml:invoke name="$FUNCTION_NAME">\n'
        '<entml:parameter name="$PARAMETER_NAME">$VALUE</entml:parameter>\n'
        "</entml:invoke>\n"
        f"现在调用：\n{READ_INVOKE}\n"
        "</entml:thinking>\n"
    )

    return [
        # --- 普通 ---
        ParserScenario(
            id="bare_read_invoke",
            text=READ_INVOKE,
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
        ),
        ParserScenario(
            id="bare_weather_multi_param",
            text=WEATHER_INVOKE,
            expect_names=("get_weather",),
            expect_args=({"city": "杭州", "unit": "c"},),
        ),
        ParserScenario(
            id="text_before_invoke",
            text=f"好的，我来读取。\n{READ_INVOKE}",
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
            expect_clean_contains=("读取",),
        ),
        ParserScenario(
            id="text_after_invoke",
            text=f"{READ_INVOKE}\n完成。",
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
            expect_clean_contains=("完成",),
        ),
        ParserScenario(
            id="thinking_then_text_then_invoke",
            text=(
                "<entml:thinking>\n需要先读脚本\n</entml:thinking>\n"
                "马上读取。\n"
                f"{READ_INVOKE}"
            ),
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
            expect_thinking_contains=("需要先读脚本",),
            expect_clean_contains=("马上读取",),
        ),
        ParserScenario(
            id="parallel_weather_and_search",
            text=(
                f"{WEATHER_INVOKE}\n"
                '<entml:invoke name="search_web">\n'
                '<entml:parameter name="query">西湖</entml:parameter>\n'
                '<entml:parameter name="limit">3</entml:parameter>\n'
                "</entml:invoke>"
            ),
            expect_names=("get_weather", "search_web"),
            expect_args=(
                {"city": "杭州", "unit": "c"},
                {"query": "西湖", "limit": 3},
            ),
        ),
        ParserScenario(
            id="only_visible_text",
            text="这是普通回复，没有工具。",
            expect_call_count=0,
            expect_clean_contains=("普通回复",),
        ),
        ParserScenario(
            id="only_thinking_block",
            text="<entml:thinking>\n纯思考\n</entml:thinking>\n",
            expect_call_count=0,
            expect_thinking_contains=("纯思考",),
        ),
        # --- fault </thinking> + 换行（rogator 高发）---
        ParserScenario(
            id="fault_close_multiline_read",
            text=f"<entml:thinking>\nplan\n</thinking>\n{READ_INVOKE}",
            tools=[READ_TOOL],
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
            expect_thinking_contains=("plan",),
            chunk_sizes=FAULT_CLOSE_CHUNKS,
            split_at_angle_brackets=True,
        ),
        ParserScenario(
            id="fault_close_weather",
            text=f"<entml:thinking>\n查天气\n</thinking>\n{WEATHER_INVOKE}",
            expect_names=("get_weather",),
            expect_args=({"city": "杭州", "unit": "c"},),
            expect_thinking_contains=("查天气",),
            chunk_sizes=FAULT_CLOSE_CHUNKS,
        ),
        # --- thinking 边界（不应解析）---
        ParserScenario(
            id="invoke_inside_unclosed_thinking",
            text=f"<entml:thinking>\nplan\n{READ_INVOKE}\n",
            tools=[READ_TOOL],
            expect_call_count=0,
            expect_thinking_contains=("plan", "cursor_agent_simple.py"),
            stream_only=True,
        ),
        ParserScenario(
            id="invoke_and_example_inside_closed_thinking",
            text=example_in_thinking,
            tools=[READ_TOOL],
            expect_call_count=0,
            expect_thinking_contains=("格式示例", "cursor_agent_simple.py"),
            stream_only=True,
        ),
        ParserScenario(
            id="mention_invoke_in_thinking_then_real_invoke",
            text=(
                "<entml:thinking>\n应使用 entml:invoke 格式\n</entml:thinking>\n"
                f"{READ_INVOKE}"
            ),
            tools=[READ_TOOL],
            expect_names=("Read",),
            expect_args=({"path": READ_PATH},),
            expect_thinking_contains=("entml:invoke",),
        ),
        ParserScenario(
            id="fault_close_without_following_invoke",
            text="<entml:thinking>\nplan\n</thinking>\nmore\n</entml:thinking>\nanswer",
            expect_call_count=0,
            expect_thinking_contains=("plan",),
            expect_clean_contains=("answer",),
        ),
        # --- 错误/非 entml 格式 ---
        ParserScenario(
            id="wrong_json_object",
            text=f'{{"name": "Read", "arguments": {{"path": "{READ_PATH}"}}}}',
            tools=[READ_TOOL],
            expect_call_count=0,
        ),
        ParserScenario(
            id="wrong_tool_block",
            text='<tool>\n{"name": "Read"}\n</tool>',
            tools=[READ_TOOL],
            expect_call_count=0,
        ),
        ParserScenario(
            id="truncated_json_fragment",
            text='{"name": "Read", "arguments": {"path":',
            tools=[READ_TOOL],
            expect_call_count=0,
        ),
        # --- 截断流 ---
        ParserScenario(
            id="truncated_after_thinking_close",
            text=(
                "<entml:thinking>ok</entml:thinking>\n"
                '<entml:invoke name="Read">\n'
                f'<entml:parameter name="path">{READ_PATH}'
            ),
            tools=[READ_TOOL],
            expect_call_count=0,
            expect_json_delta_valid=False,
            chunk_sizes=(8, 17),
        ),
        ParserScenario(
            id="truncated_invoke_open_only",
            text='<entml:invoke name="Read">',
            tools=[READ_TOOL],
            expect_call_count=0,
            expect_json_delta_valid=False,
        ),
        # --- 空/空白 ---
        ParserScenario(
            id="empty_string",
            text="",
            expect_call_count=0,
        ),
        ParserScenario(
            id="whitespace_only",
            text="  \n\t  ",
            expect_call_count=0,
        ),
    ]


SCENARIOS = _scenarios()
SCENARIO_IDS = [s.id for s in SCENARIOS]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=SCENARIO_IDS)
def test_batch_parse(scenario: ParserScenario) -> None:
    if scenario.stream_only:
        pytest.skip("batch parse 不过滤 thinking 内 invoke，见 test_batch_thinking_invoke_known_gap")
    proto = get_protocol("entml")
    clean, calls = proto.parse(scenario.text, list(scenario.tools))
    parser = FncallStreamParser(protocol=proto, tools=list(scenario.tools))
    parser.feed(scenario.text)
    _, _ = parser.finalize()
    _assert_scenario(scenario, clean, calls, parser, label="batch")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=SCENARIO_IDS)
@pytest.mark.parametrize("chunk_size", CHUNK_SIZES, ids=lambda n: f"c{n}")
def test_stream_matches_batch(scenario: ParserScenario, chunk_size: int) -> None:
    if chunk_size not in scenario.chunk_sizes:
        pytest.skip(f"chunk {chunk_size} not required for {scenario.id}")

    proto = get_protocol("entml")
    stream_clean, stream_calls, parser = _stream_parse(
        scenario.text, scenario.tools, chunk_size,
    )
    _assert_scenario(scenario, stream_clean, stream_calls, parser, label=f"stream-{chunk_size}")

    if scenario.stream_only:
        return

    batch_clean, batch_calls = proto.parse(scenario.text, list(scenario.tools))
    assert _names(stream_calls) == _names(batch_calls), scenario.id
    assert _args(stream_calls) == _args(batch_calls), scenario.id

    if batch_calls and not scenario.expect_thinking_contains:
        bdisp, _ = split_entml_thinking(batch_clean)
        sdisp, _ = split_entml_thinking(stream_clean)
        assert sdisp.strip() == bdisp.strip(), scenario.id


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.split_at_angle_brackets], ids=lambda s: s.id)
def test_split_at_every_angle_bracket(scenario: ParserScenario) -> None:
    """在每个 ``<`` 位置切开，批流结果必须一致。"""
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(scenario.text, list(scenario.tools))
    expect_names = _names(batch_calls)
    expect_args = _args(batch_calls)

    cut_points = {0, len(scenario.text)}
    for i, ch in enumerate(scenario.text):
        if ch == "<":
            cut_points.update({max(0, i - 1), i, i + 1})

    failures: List[str] = []
    for cut in sorted(cut_points):
        parser = FncallStreamParser(protocol=proto, tools=list(scenario.tools))
        if cut > 0:
            parser.feed(scenario.text[:cut])
        if cut < len(scenario.text):
            parser.feed(scenario.text[cut:])
        _, calls = parser.finalize()
        if _names(calls) != expect_names or _args(calls) != expect_args:
            failures.append(
                f"cut={cut}: got names={_names(calls)} args={_args(calls)}"
            )
        if len(failures) >= 5:
            break

    assert not failures, f"{scenario.id}:\n" + "\n".join(failures)


@pytest.mark.parametrize("chunk_size", [1, 8, 17])
def test_incremental_ready_matches_finalize(chunk_size: int) -> None:
    text = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        f"{WEATHER_INVOKE}\n"
        f"{READ_INVOKE}"
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=STANDARD_TOOLS)
    incremental: List[Dict[str, Any]] = []
    for i in range(0, len(text), chunk_size):
        incremental.extend(parser.feed(text[i : i + chunk_size]))
    _, final = parser.finalize()
    assert parser.get_ready_tool_calls() == []
    assert _names(incremental) == _names(final) == ["get_weather", "Read"]
    assert _args(incremental) == _args(final)


def test_feed_ready_not_double_consumed() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=STANDARD_TOOLS)
    ready = parser.feed(READ_INVOKE)
    assert len(ready) == 1
    assert parser.get_ready_tool_calls() == []


@pytest.mark.parametrize("chunk_size", [1, 8, 17, 64])
def test_json_delta_valid_when_invoke_complete(chunk_size: int) -> None:
    merged = _collect_json_deltas(READ_INVOKE, chunk_size)
    assert merged
    parsed = json.loads(merged)
    assert parsed == {"path": READ_PATH}


@pytest.mark.parametrize("chunk_size", [8, 17])
def test_json_delta_invalid_when_truncated(chunk_size: int) -> None:
    partial = (
        "<entml:thinking>ok</entml:thinking>\n"
        '<entml:invoke name="Read">\n'
        f'<entml:parameter name="path">{READ_PATH}'
    )
    merged = _collect_json_deltas(partial, chunk_size)
    if not merged:
        return
    with pytest.raises(json.JSONDecodeError):
        json.loads(merged)


def test_fault_close_never_empty_read_args() -> None:
    """回归：``</thinking>`` + 换行 invoke 分片不得解析成 ``{}``。"""
    text = f"<entml:thinking>\nplan\n</thinking>\n{READ_INVOKE}"
    for chunk in FAULT_CLOSE_CHUNKS:
        _, calls, _ = _stream_parse(text, [READ_TOOL], chunk)
        assert len(calls) == 1, f"chunk={chunk}"
        args = json.loads(calls[0]["function"]["arguments"])
        assert args.get("path") == READ_PATH, f"chunk={chunk} args={args!r}"
        assert args != {}, f"chunk={chunk}"


def test_finalize_is_idempotent() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=STANDARD_TOOLS)
    parser.feed(f"前缀\n{WEATHER_INVOKE}")
    r1 = parser.finalize()
    r2 = parser.finalize()
    assert r1 == r2
    assert parser.feed("more") == []


def test_thinking_stream_incremental_before_close() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=STANDARD_TOOLS)
    parser.feed("<entml:thinking>\nline1\n")
    assert "line1" in parser.partial_thinking
    assert not parser.has_calls
    parser.feed("line2\n</entml:thinking>\n")
    assert "line2" in parser.partial_thinking
    parser.feed(READ_INVOKE)
    _, calls = parser.finalize()
    assert len(calls) == 1


def test_two_sequential_thinking_blocks_only_second_tool_parsed() -> None:
    text = (
        "<entml:thinking>\nfirst\n</entml:thinking>\n"
        "middle\n"
        "<entml:thinking>\nsecond\n</entml:thinking>\n"
        f"{READ_INVOKE}"
    )
    clean, calls, parser = _stream_parse(text, [READ_TOOL], 5)
    assert len(calls) == 1
    assert "first" in parser.partial_thinking
    assert "second" in parser.partial_thinking
    assert "middle" in clean


def test_invoke_index_inside_unclosed_thinking() -> None:
    from echotools.exec.fncall.protocols.entml_think.parse import (
        find_complete_entml_invoke_open,
        invoke_index_inside_unclosed_thinking,
    )

    inside = (
        "<entml:thinking>\nplan\n"
        '<entml:invoke name="Read">\n'
        "</entml:invoke>\n"
    )
    pos = find_complete_entml_invoke_open(inside)
    assert pos >= 0
    assert invoke_index_inside_unclosed_thinking(inside, pos)

    fault = (
        "<entml:thinking>\nplan\n</thinking>\n"
        '<entml:invoke name="Read">\n'
        "</entml:invoke>"
    )
    pos2 = find_complete_entml_invoke_open(fault)
    assert pos2 >= 0
    assert not invoke_index_inside_unclosed_thinking(fault, pos2)

    closed = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        '<entml:invoke name="Read">\n'
        "</entml:invoke>"
    )
    pos3 = find_complete_entml_invoke_open(closed)
    assert pos3 >= 0
    assert not invoke_index_inside_unclosed_thinking(closed, pos3)


def test_large_chunk_invoke_inside_unclosed_thinking_zero_calls() -> None:
    """回归：首包很大且含 thinking 内 invoke 时不得进入 IN_FUNCTION_CALLS。"""
    text = f"<entml:thinking>\nplan\n{READ_INVOKE}\n"
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
    parser.feed(text[:64])
    assert parser.state == FncallStreamParser.WAITING_FOR_TAG
    assert parser._thinking_filter is not None
    assert parser._thinking_filter.in_open_thinking()
    parser.feed(text[64:])
    _, calls = parser.finalize()
    assert calls == []
    assert "cursor_agent_simple.py" in parser.partial_thinking


def test_batch_thinking_invoke_known_gap() -> None:
    """文档化：批量 parse 会解析 thinking 块内的 invoke（流式不会）。"""
    proto = get_protocol("entml")
    inside = f"<entml:thinking>\nplan\n{READ_INVOKE}\n</entml:thinking>\n"
    _, batch_calls = proto.parse(inside, [READ_TOOL])
    assert len(batch_calls) >= 1
    stream_clean, stream_calls, _ = _stream_parse(inside, [READ_TOOL], 8)
    assert len(stream_calls) == 0
    assert "entml:invoke" not in stream_clean


def test_char_by_char_all_scenarios_with_tools() -> None:
    """对有期望 tool 的流式场景做逐字符解析，必须与同场景批量结果一致或 stream_only。"""
    proto = get_protocol("entml")
    tool_scenarios = [s for s in SCENARIOS if s.expect_names and not s.stream_only]
    for scenario in tool_scenarios:
        _, batch_calls = proto.parse(scenario.text, list(scenario.tools))
        parser = FncallStreamParser(protocol=proto, tools=list(scenario.tools))
        inc: List[Dict[str, Any]] = []
        for ch in scenario.text:
            inc.extend(parser.feed(ch))
        _, final = parser.finalize()
        assert _names(inc) == _names(batch_calls), scenario.id
        assert _args(inc) == _args(batch_calls), scenario.id
        assert _names(final) == _names(batch_calls), scenario.id


def test_char_by_char_stream_only_scenarios() -> None:
    """stream_only 场景：逐字符流式仍须满足期望。"""
    for scenario in [s for s in SCENARIOS if s.stream_only]:
        parser = FncallStreamParser(
            protocol=get_protocol("entml"), tools=list(scenario.tools),
        )
        for ch in scenario.text:
            parser.feed(ch)
        clean, calls = parser.finalize()
        _assert_scenario(scenario, clean, calls, parser, label=f"char-{scenario.id}")


def test_multiline_parameter_value_preserved() -> None:
    body = "line1\nline2\nline3"
    text = (
        '<entml:invoke name="Read">\n'
        f'<entml:parameter name="path">{body}</entml:parameter>\n'
        "</entml:invoke>"
    )
    for chunk in (1, 8, 17):
        _, calls, _ = _stream_parse(text, [READ_TOOL], chunk)
        assert json.loads(calls[0]["function"]["arguments"])["path"] == body


def test_duplicate_assistant_invoke_both_parsed() -> None:
    """同一段回复内重复 invoke（无去重）均应解析。"""
    text = f"{READ_INVOKE}\n{READ_INVOKE}"
    _, calls, _ = _stream_parse(text, [READ_TOOL], 7)
    assert len(calls) == 2
    assert _names(calls) == ["Read", "Read"]


def test_legacy_function_calls_wrapper_still_parses() -> None:
    text = (
        "<entml:function_calls>\n"
        f"{WEATHER_INVOKE}\n"
        "</entml:function_calls>"
    )
    _, calls, _ = _stream_parse(text, STANDARD_TOOLS, 11)
    assert _names(calls) == ["get_weather"]


def test_scenario_corpus_covers_required_shapes() -> None:
    required = {
        "bare_read_invoke",
        "fault_close_multiline_read",
        "invoke_inside_unclosed_thinking",
        "invoke_and_example_inside_closed_thinking",
        "truncated_after_thinking_close",
        "wrong_json_object",
        "parallel_weather_and_search",
        "thinking_then_text_then_invoke",
    }
    assert required.issubset(set(SCENARIO_IDS))
