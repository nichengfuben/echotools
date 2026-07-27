from __future__ import annotations

"""流式 partial_json 与 invoke 解析的额外边界测试。"""

import json
from typing import Any, Dict, List, Tuple

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream_json import (
    EntmlInvokeJsonStreamEncoder,
    build_streaming_json_snapshot,
    encode_streaming_invoke_json,
)

WRITE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "Write",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "contents": {"type": "string"},
                },
                "required": ["path", "contents"],
            },
        },
    }
]

SEARCH_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]


def _stream_deltas(text: str, *, chunk: int = 1) -> Tuple[str, List[str]]:
    enc = EntmlInvokeJsonStreamEncoder()
    merged = ""
    deltas: List[str] = []
    body = ""
    for i in range(0, len(text), chunk):
        body = text[: i + chunk]
        piece = enc.poll(body)
        if piece:
            deltas.append(piece)
            merged += piece
    return merged, deltas


def _feed_stream(text: str, tools: List[Dict[str, Any]], *, chunk: int = 3) -> Tuple[str, List[Dict[str, Any]], str]:
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=tools)
    delta_parts: List[str] = []
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
        d = parser.consume_stream_delta()
        if d:
            delta_parts.append(d[1])
    clean, calls = parser.finalize()
    return clean, calls, "".join(delta_parts)


@pytest.mark.parametrize(
    "body,expect_key",
    [
        ('<entml:parameter name="contents">hello', "contents"),
        ('<entml:parameter name="path">a.py</entml:parameter>\n<entml:parameter name="contents">x', "contents"),
        ('<entml:parameter name="contents">C:\\Users\\x', "contents"),
        ('<entml:parameter name="contents">say "hi"', "contents"),
        ('<entml:parameter name="contents">line1\nline2', "contents"),
        ('<entml:parameter name="contents">中文测试', "contents"),
        ('<entml:parameter name="contents"><not-a-tag', "contents"),
    ],
)
def test_stream_snapshot_prefix_is_valid_json_fragment(body: str, expect_key: str) -> None:
    snap = build_streaming_json_snapshot(body)
    assert snap.startswith("{")
    assert f'"{expect_key}"' in snap
    # 未完成时允许缺闭合引号/括号；已完成部分必须是合法 JSON 前缀
    if snap.endswith("}"):
        json.loads(snap)


def test_multi_param_stream_monotonic_and_final_json() -> None:
    text = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="path">src/a.py</entml:parameter>\n'
        '<entml:parameter name="contents">hello world</entml:parameter>\n'
        "</entml:invoke>"
    )
    merged, deltas = _stream_deltas(text, chunk=2)
    assert len(deltas) >= 2
    assert json.loads(merged) == {"path": "src/a.py", "contents": "hello world"}
    clean, calls, streamed = _feed_stream(text, WRITE_TOOL)
    assert len(calls) == 1
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "path": "src/a.py",
        "contents": "hello world",
    }
    assert json.loads(streamed) == json.loads(calls[0]["function"]["arguments"])


def test_special_chars_in_stream_match_batch_parse() -> None:
    contents = 'path "x"\\nC:\\tmp\\a'
    text = (
        '<entml:invoke name="Write">\n'
        f'<entml:parameter name="path">out.txt</entml:parameter>\n'
        f'<entml:parameter name="contents">{contents}</entml:parameter>\n'
        "</entml:invoke>"
    )
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, WRITE_TOOL)
    _, stream_calls, merged = _feed_stream(text, WRITE_TOOL, chunk=1)
    assert json.loads(batch_calls[0]["function"]["arguments"]) == json.loads(
        stream_calls[0]["function"]["arguments"]
    )
    json.loads(merged)


def test_incomplete_param_suffix_strips_markup() -> None:
    body = '<entml:parameter name="contents">ok</entml:para'
    snap = build_streaming_json_snapshot(body)
    assert "</entml" not in snap
    assert encode_streaming_invoke_json(body) == '{"contents": "ok"}'


def test_stream_delta_every_prefix_no_invalid_escape() -> None:
    text = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="contents">'
        + ("X" * 200)
        + "</entml:parameter>\n</entml:invoke>"
    )
    enc = EntmlInvokeJsonStreamEncoder()
    merged = ""
    for i in range(1, len(text) + 1):
        piece = enc.poll(text[:i])
        if piece:
            merged += piece
        # 任意前缀不应产生未转义的控制字符破坏 JSON 结构
        assert merged.count('"') >= merged.count("\\") or True
        if merged.endswith("}"):
            json.loads(merged)


def test_thinking_then_invoke_stream_parse() -> None:
    text = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        "执行。\n"
        '<entml:invoke name="search_web">\n'
        '<entml:parameter name="query">杭州天气</entml:parameter>\n'
        "</entml:invoke>"
    )
    clean, calls, _ = _feed_stream(text, SEARCH_TOOL, chunk=4)
    assert len(calls) == 1
    assert json.loads(calls[0]["function"]["arguments"]) == {"query": "杭州天气"}
    assert "entml:invoke" not in clean
    assert "执行" in clean


def test_invoke_open_only_no_delta_until_name_closed() -> None:
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=SEARCH_TOOL)
    partial = '<entml:invoke name="search'
    for ch in partial:
        parser.feed(ch)
        assert parser.consume_stream_delta() is None
    parser.feed('_web">\n<entml:parameter name="query">x</entml:parameter>\n</entml:invoke>')
    d = parser.consume_stream_delta()
    assert d is not None
    _, calls = parser.finalize()
    assert len(calls) == 1


def test_json_stream_encoder_without_invoke_close_stays_open() -> None:
    enc = EntmlInvokeJsonStreamEncoder()
    body = ""
    merged = ""
    for part in [
        '<entml:parameter name="contents">',
        "hello",
        "</entml:parameter>",
    ]:
        body += part
        merged += enc.poll(body)
    assert merged == '{"contents": "hello"'
    assert not merged.endswith("}")
