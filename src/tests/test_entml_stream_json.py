from __future__ import annotations

import json

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream_json import (
    EntmlInvokeJsonStreamEncoder,
    encode_streaming_invoke_json,
)


def test_encode_partial_parameter_value() -> None:
    body = '<entml:parameter name="contents">hello wo'
    assert encode_streaming_invoke_json(body) == '{"contents": "hello wo"}'


def test_encode_complete_parameter() -> None:
    body = (
        '<entml:parameter name="contents">done</entml:parameter>\n'
        "</entml:invoke>"
    )
    assert encode_streaming_invoke_json(body) == '{"contents": "done"}'


def test_json_stream_encoder_monotonic() -> None:
    enc = EntmlInvokeJsonStreamEncoder()
    parts = [
        '<entml:parameter name="contents">',
        "hel",
        "lo",
        "</entml:parameter>",
    ]
    merged = ""
    body = ""
    for part in parts:
        body += part
        merged += enc.poll(body)
    assert json.loads(merged) == {"contents": "hello"}


def test_parser_streams_before_invoke_close() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Write",
                "parameters": {
                    "type": "object",
                    "properties": {"contents": {"type": "string"}},
                    "required": ["contents"],
                },
            },
        }
    ]
    proto = get_protocol("entml")
    text = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="contents">'
    )
    parser = FncallStreamParser(protocol=proto, tools=tools)
    deltas = []
    payload = text + ("X" * 100) + "</entml:parameter>\n</entml:invoke>"
    for i in range(0, len(payload), 10):
        parser.feed(payload[i : i + 10])
        d = parser.consume_stream_delta()
        if d:
            deltas.append(d[1])
    assert parser.consume_stream_delta() is None
    merged = "".join(deltas)
    assert '"contents"' in merged
    assert "X" * 20 in merged
    assert len(deltas) >= 2
    json.loads(merged)
    clean, calls = parser.finalize()
    assert len(calls) == 1
