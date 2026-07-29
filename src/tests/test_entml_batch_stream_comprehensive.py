from __future__ import annotations

"""entml 解析器 batch / stream 全方位 parity 与标签泄漏回归。"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest
from fixtures.simulated_fake_history_markup_responses import (
    iter_fake_history_markup_cases,
)
from fixtures.simulated_fault_thinking_responses import (
    iter_fault_thinking_cases,
    tools_for_fault_case,
)
from fixtures.simulated_llm_tool_responses import (
    TOOLS,
    iter_simulated_cases,
    tools_for_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking

_CHUNK_SIZES = (1, 3, 7, 17, 64, 0)
_TAG_LEAK_RE = re.compile(r"</?entml:", re.IGNORECASE)
_FAKE_HISTORY_BLOCK_RE = re.compile(
    r"(?:^|\n)\s*</?(?:assistant|tool)\s*>\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)

_QWEN_LOGS = Path(r"X:/Project/Public/Qwen/logs/responses")

_BASH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "description": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["command"],
            },
        },
    }
]

_GREP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "glob": {"type": "string"},
                    "output_mode": {"type": "string"},
                    "-n": {"type": "boolean"},
                    "head_limit": {"type": "integer"},
                },
                "required": ["pattern"],
            },
        },
    }
]

_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "TodoList",
            "parameters": {
                "type": "object",
                "properties": {"todos": {"type": "array"}},
                "required": ["todos"],
            },
        },
    },
]


@dataclass(frozen=True)
class CorpusCase:
    id: str
    path: Path
    tools: List[Dict[str, Any]]
    expect_min_calls: int = 1
    expect_call_names: Tuple[str, ...] = ()
    expect_display_contains: Tuple[str, ...] = ()
    expect_thinking_nonempty: bool = True


def _args(calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _names(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["function"]["name"] for c in calls]


def _assert_no_tag_leak(display: str, *, case_id: str) -> None:
    assert _TAG_LEAK_RE.search(display) is None, (
        f"{case_id}: entml tag leaked in display: {display[-200:]!r}"
    )
    assert _FAKE_HISTORY_BLOCK_RE.search(display) is None, (
        f"{case_id}: fake history block tag leaked: {display[-200:]!r}"
    )


def _batch_parse(
    text: str, tools: List[Dict[str, Any]]
) -> Tuple[str, List[Dict[str, Any]]]:
    return get_protocol("entml").parse(text, tools)


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


def _assert_batch_stream_parity(
    text: str,
    tools: List[Dict[str, Any]],
    *,
    case_id: str,
    chunk_size: int,
) -> None:
    batch_clean, batch_calls = _batch_parse(text, tools)
    stream_clean, stream_calls, stream_thinking = _stream_parse(
        text, tools, chunk_size
    )

    _assert_no_tag_leak(batch_clean, case_id=f"{case_id}/batch")
    _assert_no_tag_leak(stream_clean, case_id=f"{case_id}/stream/chunk{chunk_size}")

    assert _names(batch_calls) == _names(stream_calls), (
        f"{case_id} chunk={chunk_size}: names "
        f"batch={_names(batch_calls)} stream={_names(stream_calls)}"
    )
    assert _args(batch_calls) == _args(stream_calls), (
        f"{case_id} chunk={chunk_size}: args differ"
    )
    assert batch_clean.strip() == stream_clean.strip(), (
        f"{case_id} chunk={chunk_size}: display batch={batch_clean!r} "
        f"stream={stream_clean!r}"
    )

    _, source_thinking = split_entml_thinking(text)
    if source_thinking.strip():
        combined = "\n".join(
            part for part in (source_thinking, stream_thinking) if part
        ).strip()
        assert combined, f"{case_id}: expected thinking content"


def _corpus_cases() -> List[CorpusCase]:
    candidates = [
        CorpusCase(
            id="req-1785257460_invoke_no_tag_leak",
            path=_QWEN_LOGS / "req-1785257460-e13689ecaf85.txt",
            tools=_BASH_TOOLS,
            expect_call_names=("Bash",),
            expect_display_contains=("headers",),
        ),
        CorpusCase(
            id="req-1785255721_tool_block_fault_thinking",
            path=_QWEN_LOGS / "req-1785255721-dc06ea92d007.txt",
            tools=_AGENT_TOOLS,
            expect_call_names=("Bash",),
        ),
        CorpusCase(
            id="req-1785254073_tool_block_bash_output",
            path=_QWEN_LOGS / "req-1785254073-c2e9ac516710.txt",
            tools=_AGENT_TOOLS,
            expect_call_names=("TodoList", "Bash"),
        ),
        CorpusCase(
            id="req-1785259051_read_scalar_system_close",
            path=_QWEN_LOGS / "req-1785259051-2ba6a21f5cf4.txt",
            tools=[
                {
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
            ],
            expect_call_names=("Read",),
            expect_display_contains=("原因", "PoW"),
        ),
        CorpusCase(
            id="req-1785260732_thinking_then_bash_only",
            path=_QWEN_LOGS / "req-1785260732-7dffd1cd4122.txt",
            tools=_BASH_TOOLS,
            expect_call_names=("Bash",),
            expect_display_contains=(),
            expect_thinking_nonempty=True,
        ),
        CorpusCase(
            id="req-1785261134_bare_parameter_grep",
            path=_QWEN_LOGS / "req-1785261134-166e5f5aae53.txt",
            tools=_GREP_TOOLS,
            expect_call_names=("Grep",),
            expect_display_contains=(),
            expect_thinking_nonempty=True,
        ),
    ]
    return [c for c in candidates if c.path.is_file()]


CORPUS_CASES = _corpus_cases()


@pytest.mark.parametrize("case", iter_simulated_cases(), ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", _CHUNK_SIZES, ids=lambda n: f"chunk{n}")
def test_simulated_corpus_batch_stream_parity(case, chunk_size: int) -> None:
    tools = tools_for_case(case)
    _assert_batch_stream_parity(
        case.response, tools, case_id=case.id, chunk_size=chunk_size
    )


@pytest.mark.parametrize("case", iter_fault_thinking_cases(), ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", _CHUNK_SIZES, ids=lambda n: f"chunk{n}")
def test_fault_thinking_batch_stream_parity(case, chunk_size: int) -> None:
    tools = tools_for_fault_case(case)
    _assert_batch_stream_parity(
        case.response, tools, case_id=case.id, chunk_size=chunk_size
    )


@pytest.mark.parametrize("case", iter_fake_history_markup_cases(), ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", (1, 7, 64), ids=lambda n: f"chunk{n}")
def test_fake_history_batch_stream_no_tag_leak(case, chunk_size: int) -> None:
    _assert_batch_stream_parity(
        case.response, TOOLS, case_id=case.id, chunk_size=chunk_size
    )


@pytest.mark.skipif(not CORPUS_CASES, reason="Qwen response corpus not available")
@pytest.mark.parametrize("case", CORPUS_CASES, ids=lambda c: c.id)
@pytest.mark.parametrize("chunk_size", _CHUNK_SIZES, ids=lambda n: f"chunk{n}")
def test_qwen_corpus_batch_stream_parity(case: CorpusCase, chunk_size: int) -> None:
    text = case.path.read_text(encoding="utf-8")
    _assert_batch_stream_parity(
        text, case.tools, case_id=case.id, chunk_size=chunk_size
    )

    batch_clean, batch_calls = _batch_parse(text, case.tools)
    assert len(batch_calls) >= case.expect_min_calls, case.id
    if case.expect_call_names:
        assert _names(batch_calls) == list(case.expect_call_names), case.id
    for needle in case.expect_display_contains:
        assert needle in batch_clean, f"{case.id}: missing {needle!r}"

    _, source_thinking = split_entml_thinking(text)
    if case.expect_thinking_nonempty and "<entml:thinking" in text.lower():
        assert source_thinking.strip(), case.id


def test_batch_display_never_contains_entml_tags_on_invoke_samples() -> None:
    """invoke-only 样本：batch / stream 可见正文均不得含 entml 标签。"""
    samples = [
        (
            "plain invoke",
            '<entml:invoke name="get_weather">'
            '<entml:parameter name="city">杭州</entml:parameter>'
            "</entml:invoke>",
        ),
        (
            "thinking + invoke + prose",
            "<entml:thinking>\nplan\n</entml:thinking>\n"
            "说明。\n"
            '<entml:invoke name="get_weather">'
            '<entml:parameter name="city">杭州</entml:parameter>'
            "</entml:invoke>",
        ),
        (
            "direct child params",
            '<entml:invoke name="Bash">\n'
            "<command>echo hi</command>\n"
            "<timeout>1000</timeout>\n"
            "</entml:invoke>",
            _BASH_TOOLS,
        ),
    ]
    for label, text, *extra_tools in samples:
        tools = extra_tools[0] if extra_tools else TOOLS
        batch_clean, batch_calls = _batch_parse(text, tools)
        assert batch_calls, label
        _assert_no_tag_leak(batch_clean, case_id=f"{label}/batch")
        for chunk in (1, 16):
            stream_clean, stream_calls, _ = _stream_parse(text, tools, chunk)
            assert stream_calls, label
            _assert_no_tag_leak(stream_clean, case_id=f"{label}/stream/{chunk}")


def test_req_1785257460_batch_stream_no_thinking_tag_leak() -> None:
    """回归：batch parse 不得泄漏 ``<entml:thinking>`` 标签（req-1785257460）。"""
    path = _QWEN_LOGS / "req-1785257460-e13689ecaf85.txt"
    if not path.is_file():
        pytest.skip("corpus not available")
    text = path.read_text(encoding="utf-8")
    batch_clean, batch_calls = _batch_parse(text, _BASH_TOOLS)
    stream_clean, stream_calls, stream_thinking = _stream_parse(text, _BASH_TOOLS, 7)

    assert len(batch_calls) == 1
    assert batch_calls[0]["function"]["name"] == "Bash"
    assert "<entml:thinking" not in batch_clean.lower()
    assert "entml:" not in batch_clean.lower()
    assert batch_clean.strip() == stream_clean.strip()
    assert len(stream_thinking) > 500


def test_req_1785259051_read_scalar_and_no_angle_leak() -> None:
    """回归：``{Read: path}`` + ``</system>`` 伪块须解析 Read；流式不得先吐出 ``<``。"""
    path = _QWEN_LOGS / "req-1785259051-2ba6a21f5cf4.txt"
    if not path.is_file():
        pytest.skip("corpus not available")
    read_tools = [
        {
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
    ]
    text = path.read_text(encoding="utf-8")
    batch_clean, batch_calls = _batch_parse(text, read_tools)
    assert len(batch_calls) == 1
    assert batch_calls[0]["function"]["name"] == "Read"
    assert "pow.py" in batch_calls[0]["function"]["arguments"]
    assert "原因" in batch_clean
    assert "entml:" not in batch_clean.lower()

    early = FncallStreamParser(protocol=get_protocol("entml"), tools=read_tools)
    for ch in text[:12]:
        early.feed(ch)
        assert early.partial_text not in (
            "<",
            "<e",
            "<en",
            "<ent",
            "<entm",
            "<entml",
            "<entml:",
        )
    stream_clean, stream_calls, stream_thinking = _stream_parse(text, read_tools, 7)
    assert len(stream_calls) == 1
    assert stream_clean.strip() == batch_clean.strip()
    assert len(stream_thinking) > 100


def _assert_no_partial_angle_leak(
    parser: FncallStreamParser,
    *,
    case_id: str,
    step: str,
) -> None:
    pt = parser.partial_text
    assert pt not in ("<", "<e", "<en", "<ent", "<entm", "<entml", "<entml:"), (
        f"{case_id}/{step}: partial_text leaked angle prefix: {pt!r}"
    )
    assert _TAG_LEAK_RE.search(pt) is None, (
        f"{case_id}/{step}: entml tag in partial_text: {pt!r}"
    )
    if pt.strip() in ("<", ">"):
        pytest.fail(f"{case_id}/{step}: lone markup char in partial_text: {pt!r}")


def test_req_1785260732_thinking_bash_no_partial_leak() -> None:
    """回归：thinking+tool 无可见回复时，流式 partial_text 不得泄漏 ``<`` / orphan 闭标签。"""
    path = _QWEN_LOGS / "req-1785260732-7dffd1cd4122.txt"
    if not path.is_file():
        pytest.skip("corpus not available")
    text = path.read_text(encoding="utf-8")
    batch_clean, batch_calls = _batch_parse(text, _BASH_TOOLS)
    assert len(batch_calls) == 1
    assert batch_calls[0]["function"]["name"] == "Bash"
    assert "GetCompletion" in batch_calls[0]["function"]["arguments"]
    assert batch_clean.strip() == ""
    assert "entml:" not in batch_clean.lower()

    for chunk_size in (1, 3, 7, 17, 64):
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=_BASH_TOOLS)
        if chunk_size <= 0:
            parser.feed(text)
            _assert_no_partial_angle_leak(
                parser, case_id="req-1785260732", step="whole"
            )
        else:
            for i in range(0, len(text), chunk_size):
                parser.feed(text[i : i + chunk_size])
                _assert_no_partial_angle_leak(
                    parser,
                    case_id="req-1785260732",
                    step=f"chunk{chunk_size}@{i}",
                )
        stream_clean, stream_calls = parser.finalize()
        stream_thinking = parser.partial_thinking
        assert len(stream_calls) == 1
        assert stream_calls[0]["function"]["name"] == "Bash"
        assert stream_clean.strip() == batch_clean.strip()
        assert len(stream_thinking) > 500

    # Qwen SSE 分 phase：thinking 已走 reasoning 通道，answer 以 orphan 闭标签开头
    import re

    m = re.match(r"<entml:thinking>[\s\S]*?</entml:thinking>([\s\S]*)", text)
    assert m
    answer_only = "</entml:thinking>" + m.group(1)
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=_BASH_TOOLS)
    for i, ch in enumerate(answer_only):
        parser.feed(ch)
        _assert_no_partial_angle_leak(
            parser, case_id="req-1785260732/qwen-split", step=f"@{i}"
        )
    stream_clean, stream_calls = parser.finalize()
    assert len(stream_calls) == 1
    assert stream_clean.strip() == ""


def test_req_1785261134_bare_parameter_stream_json_parity() -> None:
    """回归：裸 ``<parameter>`` 流式 partial_json 不得把 ``</parameter>`` 拼进 JSON 值。"""
    path = _QWEN_LOGS / "req-1785261134-166e5f5aae53.txt"
    if not path.is_file():
        pytest.skip("corpus not available")
    text = path.read_text(encoding="utf-8")
    batch_clean, batch_calls = _batch_parse(text, _GREP_TOOLS)
    assert len(batch_calls) == 1
    assert batch_calls[0]["function"]["name"] == "Grep"
    batch_args = json.loads(batch_calls[0]["function"]["arguments"])
    assert "createConnectTransport" in batch_args["pattern"]
    assert batch_args["-n"] is True
    # fault ``</thinking>`` 与 ``</entml:thinking>`` 之间的中文为可见正文（2.3.86+）
    assert "Connect-RPC" in batch_clean
    assert "entml:invoke" not in batch_clean
    assert "parameter" not in batch_clean

    for chunk_size in (1, 7, 17, 64):
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=_GREP_TOOLS)
        merged = ""
        for i in range(0, len(text), chunk_size):
            parser.feed(text[i : i + chunk_size])
            while True:
                delta = parser.consume_stream_delta()
                if not delta:
                    break
                merged += delta[1]
            assert "</parameter>" not in merged, (
                f"chunk={chunk_size}@{i}: </parameter> leaked into stream JSON"
            )
        stream_clean, stream_calls = parser.finalize()
        assert len(stream_calls) == 1
        assert merged == stream_calls[0]["function"]["arguments"]
        assert json.loads(merged) == batch_args
        assert stream_clean.strip() == batch_clean.strip()
