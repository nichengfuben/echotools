from __future__ import annotations

"""对抗性分片：在每个字符边界切开模拟 LLM 响应，确保批流一致且无标签泄露。"""

import json
from typing import Any, Dict, List

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import (
    has_unclosed_entml_thinking,
    split_entml_thinking,
)

from fixtures.simulated_llm_tool_responses import (
    SIMULATED_LLM_RESPONSES,
    TOOLS,
)


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _norm(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())


CRITICAL_IDS = [
    "thinking_then_wrapper",
    "parallel_two_tools",
    "markdown_fenced_xml",
    "history_style_tool_block_must_not_parse",
    "prose_then_tool_then_prose_attempt",
    "three_tools_mixed_styles",
    "type_attrs_reordered",
    "single_quotes_everywhere",
    "escaped_underscore_name",
    "boolean_like_strings_stay_string_when_schema_string",
]


@pytest.mark.parametrize(
    "case",
    [c for c in SIMULATED_LLM_RESPONSES if c.id in CRITICAL_IDS],
    ids=lambda c: c.id,
)
def test_adversarial_every_split_point(case) -> None:
    """对关键语料在每个字符位置切开，批流调用与正文必须一致。"""
    proto = get_protocol("entml")
    batch_clean, batch_calls = proto.parse(case.response, TOOLS)
    batch_display, _ = split_entml_thinking(batch_clean)
    expect_names = _names(batch_calls)
    expect_args = _args(batch_calls)
    expect_display = _norm(batch_display)

    text = case.response
    failures = []
    # 全量切点对长文本较慢；步进覆盖 + 边界密集
    cut_points = set(range(0, len(text), max(1, len(text) // 40)))
    cut_points.update({0, 1, 2, 3, max(0, len(text) // 2), len(text) - 1, len(text)})
    # 所有 `<` 出现处前后各 1 字符——历史 bug 高发区
    for i, ch in enumerate(text):
        if ch == "<":
            cut_points.update({i, i + 1, max(0, i - 1)})

    for cut in sorted(cut_points):
        if cut < 0 or cut > len(text):
            continue
        parser = FncallStreamParser(protocol=proto, tools=TOOLS)
        if cut > 0:
            parser.feed(text[:cut])
        if cut < len(text):
            parser.feed(text[cut:])
        clean, calls = parser.finalize()
        display, _ = split_entml_thinking(clean)
        if _names(calls) != expect_names or _args(calls) != expect_args:
            failures.append(
                f"cut={cut}: calls got={_args(calls)} expect={expect_args}"
            )
        if _norm(display) != expect_display:
            failures.append(
                f"cut={cut}: display got={display!r} expect={batch_display!r}"
            )
        for banned in ("entml:invoke", "entml:parameter", "entml:function_calls"):
            if banned in display:
                failures.append(f"cut={cut}: leaked {banned}")
        if len(failures) > 8:
            break

    assert not failures, f"{case.id}:\n" + "\n".join(failures)


def test_ambiguous_prefix_not_claimed_by_thinking() -> None:
    assert not has_unclosed_entml_thinking("hello <e")
    assert not has_unclosed_entml_thinking("hello <en")
    assert not has_unclosed_entml_thinking("hello <entml:")
    assert not has_unclosed_entml_thinking("hello <entml:i")
    assert not has_unclosed_entml_thinking("hello <entml:f")
    # 已分叉到 thinking
    assert has_unclosed_entml_thinking("hello <entml:t")
    assert has_unclosed_entml_thinking("hello <entml:thinking")
    assert has_unclosed_entml_thinking("<entml:thinking>x")


def test_split_at_closing_angle_of_parameter() -> None:
    """专门回归：在 `</entml:parameter>` 的 `<` 处切开。"""
    text = (
        "可见\n"
        '<entml:invoke name="get_weather">\n'
        '<entml:parameter name="city">杭州</entml:parameter>\n'
        '<entml:parameter name="unit">c</entml:parameter>\n'
        "</entml:invoke>"
    )
    idx = text.index("</entml:parameter>")
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=TOOLS)
    parser.feed(text[:idx])
    parser.feed(text[idx:])
    clean, calls = parser.finalize()
    assert _args(calls) == [{"city": "杭州", "unit": "c"}]
    assert "entml:" not in clean
    assert "可见" in clean


def test_raw_buf_equals_concat_for_adversarial_feed() -> None:
    case = next(c for c in SIMULATED_LLM_RESPONSES if c.id == "thinking_then_wrapper")
    proto = get_protocol("entml")
    text = case.response
    for cut in (1, 17, 41, 63, 64, 65, 100):
        parser = FncallStreamParser(protocol=proto, tools=TOOLS)
        parser.feed(text[:cut])
        parser.feed(text[cut:])
        assert parser._raw_buf == text
        clean, calls = parser.finalize()
        assert _names(calls) == case.expect_names
        assert _args(calls) == case.expect_args
        display, _ = split_entml_thinking(clean)
        assert "entml:invoke" not in display
