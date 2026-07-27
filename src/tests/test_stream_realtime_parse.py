from __future__ import annotations

"""流式实时解析：不漏检、增量就绪、与批量一致。"""

import json
from typing import Any, Dict, List

import pytest
from fixtures.simulated_llm_tool_responses import (
    SIMULATED_LLM_RESPONSES,
    TOOLS,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())


@pytest.mark.parametrize("case", SIMULATED_LLM_RESPONSES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", [1, 5, 17, 64], ids=lambda n: f"c{n}")
def test_stream_finalize_never_misses_batch(case, chunk_size: int) -> None:
    proto = get_protocol("entml")
    batch_clean, batch_calls = proto.parse(case.response, TOOLS)
    parser = FncallStreamParser(protocol=proto, tools=TOOLS)
    for i in range(0, len(case.response), chunk_size):
        parser.feed(case.response[i : i + chunk_size])
    clean, calls = parser.finalize()
    assert _names(calls) == _names(batch_calls) == case.expect_names
    assert _args(calls) == _args(batch_calls) == case.expect_args
    bdisp, _ = split_entml_thinking(batch_clean)
    sdisp, _ = split_entml_thinking(clean)
    assert _norm(sdisp) == _norm(bdisp)
    assert "entml:invoke" not in sdisp


def test_feed_returns_ready_tool_calls_incrementally() -> None:
    case = next(c for c in SIMULATED_LLM_RESPONSES if c.id == "parallel_two_tools")
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=TOOLS)
    incremental: List[Dict[str, Any]] = []
    for i in range(0, len(case.response), 3):
        ready = parser.feed(case.response[i : i + 3])
        incremental.extend(ready)
    clean, final = parser.finalize()
    # finalize 后不应再重复返回已发射的 calls
    assert parser.get_ready_tool_calls() == []
    assert _names(incremental) == case.expect_names
    assert _args(incremental) == case.expect_args
    assert _names(final) == case.expect_names
    assert _args(final) == case.expect_args
    assert "entml:invoke" not in clean


def test_ready_emitted_before_stream_ends() -> None:
    """第一个 invoke 闭合后、第二个尚未完成时即可实时取出。"""
    text = (
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">杭州</entml:parameter>'
        "</entml:invoke>"
        "中间过渡"
        '<entml:invoke name="search_web">'
        '<entml:parameter name="query">西湖</entml:parameter>'
        '<entml:parameter name="limit">2</entml:parameter>'
        "</entml:invoke>"
    )
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=TOOLS)
    first_close = text.index("</entml:invoke>") + len("</entml:invoke>")
    ready1 = []
    for ch in text[:first_close]:
        ready1.extend(parser.feed(ch))
    assert _names(ready1) == ["get_weather"]
    assert _args(ready1) == [{"city": "杭州"}]
    # 第二段未完成前不应冒出 search
    mid = text[first_close : text.index("limit")]
    ready_mid = []
    for ch in mid:
        ready_mid.extend(parser.feed(ch))
    assert ready_mid == []
    ready2 = []
    for ch in text[first_close + len(mid) :]:
        ready2.extend(parser.feed(ch))
    assert _names(ready2) == ["search_web"]
    assert _args(ready2) == [{"query": "西湖", "limit": 2}]
    _, final = parser.finalize()
    assert len(final) == 2


def test_char_by_char_ready_matches_final_for_all_tool_cases() -> None:
    proto = get_protocol("entml")
    for case in SIMULATED_LLM_RESPONSES:
        if not case.expect_names:
            continue
        parser = FncallStreamParser(protocol=proto, tools=TOOLS)
        incremental: List[Dict[str, Any]] = []
        for ch in case.response:
            incremental.extend(parser.feed(ch))
        _, final = parser.finalize()
        assert _names(incremental) == _names(final) == case.expect_names, case.id
        assert _args(incremental) == _args(final) == case.expect_args, case.id


def test_unclosed_thinking_invoke_parsed_once_inside_block() -> None:
    proto = get_protocol("entml")
    tools = TOOLS
    invoke = (
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">杭州</entml:parameter>'
        "</entml:invoke>"
    )
    parser = FncallStreamParser(protocol=proto, tools=tools)
    ready = []
    for ch in f"<entml:thinking>\nplan {invoke}\n":
        ready.extend(parser.feed(ch))
    assert len(ready) == 1
    for ch in f"</entml:thinking>\n可见\n{invoke}":
        ready.extend(parser.feed(ch))
    ready.extend(parser.get_ready_tool_calls())
    _, final = parser.finalize()
    # thinking 内第一次 invoke 已解析；闭合后重复 invoke 会再解析一次
    assert _names(final) == ["get_weather", "get_weather"]
    assert len(final) == 2
