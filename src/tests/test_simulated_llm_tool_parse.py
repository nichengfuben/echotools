from __future__ import annotations

"""用模拟 LLM 完整响应对 entml 工具解析做全方位回归。"""

import json
from typing import Any, Dict, List, Tuple

import pytest
from fixtures.simulated_llm_tool_responses import (
    SIMULATED_LLM_RESPONSES,
    TOOLS,
    SimulatedCase,
    iter_simulated_cases,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _normalize_ws(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())


def _assert_case_result(
    case: SimulatedCase,
    clean: str,
    calls: List[Dict[str, Any]],
    *,
    thinking_extra: str = "",
) -> None:
    assert _names(calls) == case.expect_names, case.id
    assert _args(calls) == case.expect_args, case.id

    display, thinking = split_entml_thinking(clean)
    combined_thinking = "\n".join(
        part for part in (thinking, thinking_extra) if part
    ).strip()

    for needle in case.expect_clean_substrings:
        assert needle in display or needle in clean, f"{case.id}: missing {needle!r}"

    for banned in case.expect_clean_absent:
        assert banned not in display, f"{case.id}: leaked {banned!r} in {display!r}"

    if case.expect_thinking is not None:
        assert case.expect_thinking in combined_thinking, (
            f"{case.id}: thinking={combined_thinking!r}"
        )


def _stream_parse(
    text: str,
    tools: List[Dict[str, Any]],
    chunk_size: int,
) -> Tuple[str, List[Dict[str, Any]], str]:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    if chunk_size <= 0:
        parser.feed(text)
    else:
        for i in range(0, len(text), chunk_size):
            parser.feed(text[i : i + chunk_size])
    clean, calls = parser.finalize()
    return clean, calls, parser.partial_thinking


@pytest.mark.parametrize("case", iter_simulated_cases(), ids=lambda c: c.id)
def test_simulated_llm_response_batch_parse(case: SimulatedCase) -> None:
    proto = get_protocol("entml")
    clean, calls = proto.parse(case.response, TOOLS)
    _assert_case_result(case, clean, calls)


@pytest.mark.parametrize("case", iter_simulated_cases(), ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", [1, 3, 7, 16, 64, 0], ids=lambda n: f"chunk{n}")
def test_simulated_llm_response_stream_chunks(case: SimulatedCase, chunk_size: int) -> None:
    clean, calls, thinking = _stream_parse(case.response, TOOLS, chunk_size)
    _assert_case_result(case, clean, calls, thinking_extra=thinking)


def test_simulated_corpus_covers_key_shapes() -> None:
    ids = {c.id for c in SIMULATED_LLM_RESPONSES}
    required = {
        "thinking_then_wrapper",
        "parallel_two_tools",
        "type_attrs_reordered",
        "single_quotes_everywhere",
        "markdown_fenced_xml",
        "escaped_underscore_name",
        "parameters_json_block",
        "multiline_shell_command",
        "history_style_tool_block_must_not_parse",
        "three_tools_mixed_styles",
    }
    assert required.issubset(ids)
    assert len(SIMULATED_LLM_RESPONSES) >= 18


def test_simulated_batch_and_stream_agree_on_all_cases() -> None:
    proto = get_protocol("entml")
    mismatches = []
    for case in SIMULATED_LLM_RESPONSES:
        batch_clean, batch_calls = proto.parse(case.response, TOOLS)
        stream_clean, stream_calls, _ = _stream_parse(case.response, TOOLS, 5)
        batch_display, _ = split_entml_thinking(batch_clean)
        stream_display, _ = split_entml_thinking(stream_clean)
        if _names(batch_calls) != _names(stream_calls) or _args(batch_calls) != _args(
            stream_calls
        ):
            mismatches.append(f"{case.id}: calls batch={_args(batch_calls)} stream={_args(stream_calls)}")
        if _normalize_ws(batch_display) != _normalize_ws(stream_display):
            mismatches.append(
                f"{case.id}: clean batch={batch_display!r} stream={stream_display!r}"
            )
    assert not mismatches, "\n".join(mismatches)


def test_generated_noisy_variants_do_not_leak_tags() -> None:
    """程序化生成噪声变体：随机夹杂空白 / 外壳 / thinking。"""
    proto = get_protocol("entml")
    cores = [
        (
            "get_weather",
            '<entml:parameter name="city">苏州</entml:parameter>'
            '<entml:parameter name="days">2</entml:parameter>',
            {"city": "苏州", "days": 2},
        ),
        (
            "search_web",
            '<entml:parameter name="query">拙政园</entml:parameter>'
            '<entml:parameter name="limit">2</entml:parameter>',
            {"query": "拙政园", "limit": 2},
        ),
    ]
    wrappers = [
        lambda body: body,
        lambda body: f"<entml:function_calls>\n{body}\n</entml:function_calls>",
        lambda body: f"```xml\n{body}\n```",
        lambda body: f"<entml:thinking>\nplan\n</entml:thinking>\n可见\n{body}",
    ]
    for name, params, expect in cores:
        invoke = f'<entml:invoke name="{name}">\n{params}\n</entml:invoke>'
        for wrap in wrappers:
            text = wrap(invoke)
            clean, calls = proto.parse(text, TOOLS)
            assert _names(calls) == [name]
            assert _args(calls)[0] == expect
            display, _ = split_entml_thinking(clean)
            assert "entml:invoke" not in display
            assert "entml:parameter" not in display
            assert "entml:function_calls" not in display

            for chunk in (1, 8, 23):
                sclean, scalls, _ = _stream_parse(text, TOOLS, chunk)
                assert _args(scalls)[0] == expect
                sdisplay, _ = split_entml_thinking(sclean)
                assert "entml:invoke" not in sdisplay
