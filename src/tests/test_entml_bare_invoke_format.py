from __future__ import annotations

"""裸 ``<entml:invoke>`` 格式全方位测试 — 与 ``_ENTML_INSTRUCTION`` 示例严格对齐。"""

import json
import re
from typing import Any, Dict, List, Tuple

import pytest
from fixtures.simulated_llm_tool_responses import (
    SimulatedCase,
    iter_bare_invoke_cases,
    tools_for_case,
)

from echotools.exec.fncall import get_protocol, inject_fncall
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml import EntmlProtocol
from echotools.exec.fncall.protocols.entml_tool.invoke import format_entml_tool_calls
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking

# 与 entml.py _ENTML_INSTRUCTION 中示例块逐行一致
INSTRUCTION_SINGLE_INVOKE_BLOCK = """\
<entml:invoke name="$FUNCTION_NAME">
<entml:parameter name="$PARAMETER_NAME">$PARAMETER_VALUE</entml:parameter>
...
</entml:invoke>"""

INSTRUCTION_DUAL_INVOKE_TAIL = """\
<entml:invoke name="$FUNCTION_NAME2">
...
</entml:invoke>"""

INSTRUCTION_KEY_LINES = (
    'writing a "<entml:invoke>" block like the following',
    '<entml:invoke name="$FUNCTION_NAME">',
    '<entml:parameter name="$PARAMETER_NAME">$PARAMETER_VALUE</entml:parameter>',
    "</entml:invoke>",
    '<entml:invoke name="$FUNCTION_NAME2">',
    "String and scalar parameters should be specified as is",
)

BANNED_IN_USER_VISIBLE = (
    "entml:invoke",
    "entml:parameter",
    "entml:function_calls",
    "function_calls",
)

_INVOKE_DOCUMENT_RE = re.compile(
    r"(?:\s*<entml:invoke\b[^>]*>[\s\S]*?</entml:invoke>\s*)+",
    re.MULTILINE,
)
_INVOKE_OPEN_RE = re.compile(
    r'<entml:invoke\b[^>]*\bname\s*=\s*["\'][^"\']+["\'][^>]*>',
    re.IGNORECASE,
)
_PARAM_BLOCK_RE = re.compile(
    r'<entml:parameter\b[^>]*\bname\s*=\s*["\'][^"\']+["\'][^>]*>'
    r"[\s\S]*?</entml:parameter>",
    re.IGNORECASE,
)

SAMPLE_TOOLS: List[Dict[str, Any]] = [
    {
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
    },
    {
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
    },
]


def _proto() -> EntmlProtocol:
    return get_protocol("entml")  # type: ignore[return-value]


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _stream_parse(
    text: str,
    tools: List[Dict[str, Any]],
    chunk_size: int,
) -> Tuple[str, List[Dict[str, Any]], str]:
    parser = FncallStreamParser(protocol=_proto(), tools=tools)
    if chunk_size <= 0:
        parser.feed(text)
    else:
        for i in range(0, len(text), chunk_size):
            parser.feed(text[i : i + chunk_size])
    clean, calls = parser.finalize()
    return clean, calls, parser.partial_thinking


def assert_bare_invoke_document(text: str) -> None:
    """文本应仅由若干裸 invoke 块组成（允许首尾空白）。"""
    stripped = text.strip()
    assert stripped, "empty invoke document"
    assert "function_calls" not in stripped
    remainder = _INVOKE_DOCUMENT_RE.sub("", stripped)
    assert not remainder.strip(), f"non-invoke residue: {remainder!r}"
    opens = list(_INVOKE_OPEN_RE.finditer(stripped))
    assert opens, "no invoke open tags"
    for m in opens:
        block_end = stripped.find("</entml:invoke>", m.start())
        assert block_end >= 0, "unclosed invoke"
        body = stripped[m.end() : block_end]
        if body.strip() and body.strip() != "...":
            assert _PARAM_BLOCK_RE.search(body), f"invoke body missing parameters: {body!r}"


def _dual_invoke_response() -> str:
    """与提示词双 invoke 示例同形的可解析语料。"""
    return (
        "我来查一下。\n"
        '<entml:invoke name="get_weather">\n'
        '<entml:parameter name="city">杭州</entml:parameter>\n'
        '<entml:parameter name="unit">c</entml:parameter>\n'
        "</entml:invoke>\n"
        '<entml:invoke name="search_web">\n'
        '<entml:parameter name="query">西湖</entml:parameter>\n'
        '<entml:parameter name="limit">3</entml:parameter>\n'
        "</entml:invoke>"
    )


class TestInstructionAlignment:
    def test_instruction_contains_canonical_blocks(self) -> None:
        prompt = _proto().render_prompt(
            tool_descs=_proto().format_tool_descs(SAMPLE_TOOLS),
            lang="en",
            current_user_message="hello",
        )
        assert INSTRUCTION_SINGLE_INVOKE_BLOCK in prompt
        assert INSTRUCTION_DUAL_INVOKE_TAIL in prompt
        for line in INSTRUCTION_KEY_LINES:
            assert line in prompt

    def test_instruction_never_mentions_function_calls(self) -> None:
        prompt = _proto().render_prompt(
            tool_descs=_proto().format_tool_descs(SAMPLE_TOOLS),
            lang="en",
            current_user_message="hello",
        )
        assert "function_calls" not in prompt.lower()

    def test_inject_fncall_prompt_same_shape(self) -> None:
        messages = [{"role": "user", "content": "查杭州天气"}]
        prompt = inject_fncall(messages, SAMPLE_TOOLS, _proto())[0]["content"]
        assert INSTRUCTION_SINGLE_INVOKE_BLOCK in prompt
        assert "function_calls" not in prompt.lower()
        assert '<entml:invoke name="$FUNCTION_NAME">' in prompt


class TestRenderShape:
    def test_format_tool_calls_is_bare_invoke_only(self) -> None:
        rendered = format_entml_tool_calls(
            [
                {
                    "id": "call_0000",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "杭州", "unit": "c"}),
                    },
                },
                {
                    "id": "call_0001",
                    "type": "function",
                    "function": {
                        "name": "search_web",
                        "arguments": json.dumps({"query": "西湖", "limit": 3}),
                    },
                },
            ]
        )
        assert_bare_invoke_document(rendered)
        assert rendered.count("<entml:invoke") == 2
        assert rendered.count("</entml:invoke>") == 2
        assert "function_calls" not in rendered

    def test_render_roundtrip_dual_invoke(self) -> None:
        original_calls = [
            {
                "id": "call_0000",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"city": "杭州", "unit": "c"}),
                },
            },
            {
                "id": "call_0001",
                "type": "function",
                "function": {
                    "name": "search_web",
                    "arguments": json.dumps({"query": "西湖", "limit": 3}),
                },
            },
        ]
        rendered = format_entml_tool_calls(original_calls)
        assert_bare_invoke_document(rendered)
        clean, parsed = _proto().parse(rendered, SAMPLE_TOOLS)
        assert clean == ""
        assert _names(parsed) == ["get_weather", "search_web"]
        assert _args(parsed) == [
            {"city": "杭州", "unit": "c"},
            {"query": "西湖", "limit": 3},
        ]


class TestBatchParse:
    def test_dual_invoke_with_prose(self) -> None:
        text = _dual_invoke_response()
        clean, calls = _proto().parse(text, SAMPLE_TOOLS)
        assert _names(calls) == ["get_weather", "search_web"]
        assert _args(calls) == [
            {"city": "杭州", "unit": "c"},
            {"query": "西湖", "limit": 3},
        ]
        assert clean.strip() == "我来查一下。"
        for banned in BANNED_IN_USER_VISIBLE:
            assert banned not in clean

    @pytest.mark.parametrize("case", iter_bare_invoke_cases(), ids=lambda c: c.id)
    def test_bare_invoke_corpus_batch(self, case: SimulatedCase) -> None:
        case_tools = tools_for_case(case)
        clean, calls = _proto().parse(case.response, case_tools)
        assert _names(calls) == case.expect_names, case.id
        assert _args(calls) == case.expect_args, case.id
        for banned in BANNED_IN_USER_VISIBLE:
            assert banned not in clean, f"{case.id} leaked {banned}"


class TestStreamParse:
    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 7, 13, 64, 0])
    def test_dual_invoke_all_chunk_sizes(self, chunk_size: int) -> None:
        text = _dual_invoke_response()
        clean, calls, _ = _stream_parse(text, SAMPLE_TOOLS, chunk_size)
        assert _names(calls) == ["get_weather", "search_web"]
        assert _args(calls) == [
            {"city": "杭州", "unit": "c"},
            {"query": "西湖", "limit": 3},
        ]
        assert clean.strip() == "我来查一下。"
        for banned in BANNED_IN_USER_VISIBLE:
            assert banned not in clean

    @pytest.mark.parametrize("case", iter_bare_invoke_cases(), ids=lambda c: c.id)
    @pytest.mark.parametrize("chunk_size", [1, 5, 17, 0], ids=lambda n: f"chunk{n}")
    def test_bare_invoke_corpus_stream(self, case: SimulatedCase, chunk_size: int) -> None:
        case_tools = tools_for_case(case)
        clean, calls, thinking = _stream_parse(case.response, case_tools, chunk_size)
        assert _names(calls) == case.expect_names, case.id
        assert _args(calls) == case.expect_args, case.id
        for banned in BANNED_IN_USER_VISIBLE:
            assert banned not in clean, f"{case.id} leaked {banned} in clean"
        if case.expect_thinking:
            assert case.expect_thinking in thinking, case.id

    def test_batch_and_stream_agree_on_bare_corpus(self) -> None:
        mismatches: List[str] = []
        for case in iter_bare_invoke_cases():
            case_tools = tools_for_case(case)
            batch_clean, batch_calls = _proto().parse(case.response, case_tools)
            stream_clean, stream_calls, _ = _stream_parse(case.response, case_tools, 5)
            batch_display, _ = split_entml_thinking(batch_clean)
            stream_display, _ = split_entml_thinking(stream_clean)
            if _names(batch_calls) != _names(stream_calls):
                mismatches.append(f"{case.id}: names differ")
            if _args(batch_calls) != _args(stream_calls):
                mismatches.append(f"{case.id}: args differ")
            if batch_display.strip() != stream_display.strip():
                mismatches.append(
                    f"{case.id}: clean batch={batch_display!r} stream={stream_display!r}"
                )
        assert not mismatches, "\n".join(mismatches)

    def test_incremental_ready_tool_calls_dual_invoke(self) -> None:
        invoke1 = (
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            '<entml:parameter name="unit">c</entml:parameter>\n'
            "</entml:invoke>\n"
        )
        invoke2 = (
            '<entml:invoke name="search_web">\n'
            '<entml:parameter name="query">西湖</entml:parameter>\n'
            '<entml:parameter name="limit">3</entml:parameter>\n'
            "</entml:invoke>"
        )
        parser = FncallStreamParser(protocol=_proto(), tools=SAMPLE_TOOLS)
        assert parser.get_ready_tool_calls() == []
        parser.feed("我来查一下。\n")
        assert parser.get_ready_tool_calls() == []
        ready1 = parser.feed(invoke1)
        assert len(ready1) == 1
        assert ready1[0]["function"]["name"] == "get_weather"
        assert parser.get_ready_tool_calls() == []
        ready2 = parser.feed(invoke2)
        assert len(ready2) == 1
        assert ready2[0]["function"]["name"] == "search_web"
        clean, calls = parser.finalize()
        assert len(calls) == 2
        assert clean.strip() == "我来查一下。"


class TestDetectAndHoldback:
    def test_detect_start_requires_name_and_closing_angle(self) -> None:
        proto = _proto()
        assert proto.detect_start('<entml:invoke name="get_weather">', tools=SAMPLE_TOOLS) == (
            True,
            0,
        )
        assert proto.detect_start('<entml:invoke name="x">', tools=SAMPLE_TOOLS) == (
            False,
            -1,
        )
        assert proto.detect_start('<entml:invoke name="get_weather"', tools=SAMPLE_TOOLS) == (
            False,
            -1,
        )
        assert proto.detect_start("<entml:invoke>", tools=SAMPLE_TOOLS) == (False, -1)
        assert proto.detect_start('<entml:invoke other="y">', tools=SAMPLE_TOOLS) == (
            False,
            -1,
        )
        assert proto.detect_start('<entml:invoke name="get_weather">', tools=None) == (
            True,
            0,
        )

    def test_holdback_until_invoke_stable(self) -> None:
        parser = FncallStreamParser(protocol=_proto(), tools=SAMPLE_TOOLS)
        parser.feed('说明文字\n<entml:invoke name=')
        assert not parser.has_calls
        assert parser.partial_text in ("说明文字\n", "说明文字")
        parser.feed('"get_weather">')
        assert parser.has_calls
        assert "entml:" not in parser.partial_text
        parser.feed(
            '<entml:parameter name="city">杭</entml:parameter></entml:invoke>'
        )
        clean, calls = parser.finalize()
        assert clean == "说明文字"
        assert _names(calls) == ["get_weather"]

    def test_trigger_tags_invoke_only(self) -> None:
        tags = _proto().get_trigger_tags()
        joined = " ".join(tags)
        assert "invoke" in joined
        assert "function_calls" not in joined


class TestCorpusCoverage:
    def test_bare_invoke_corpus_is_substantial(self) -> None:
        bare = iter_bare_invoke_cases()
        ids = {c.id for c in bare}
        required = {
            "canonical_bare_invoke",
            "parallel_two_tools_bare",
            "thinking_then_bare_invoke",
            "type_attrs_reordered",
            "single_quotes_everywhere",
        }
        assert required.issubset(ids)
        assert len(bare) >= 15
