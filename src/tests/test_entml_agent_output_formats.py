from __future__ import annotations

"""模型/agent 常见输出格式：正确 entml:invoke vs 错误 JSON/旧格式。"""

import json

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get current time",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

VALID_INVOKE = (
    '<entml:invoke name="Read">\n'
    '<entml:parameter name="path">C:/Users/Administrator/cursor_agent_simple.py</entml:parameter>\n'
    "</entml:invoke>"
)

WRONG_JSON_TOOL = (
    '{"name": "Read", "arguments": {"path": "C:/Users/Administrator/cursor_agent_simple.py"}}'
)

WRONG_TOOL_BLOCK = (
    "<tool>\n"
    '{"name": "Read", "arguments": {"path": "x.py"}}\n'
    "</tool>"
)

FAKE_PARTIAL_JSON = '{"name": "Read", "arguments": {"path":'


def _parse_batch(text: str):
    proto = get_protocol("entml")
    clean, calls = proto.parse(text, TOOLS)
    return clean, calls


def _parse_stream(text: str, *, chunk: int = 3):
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=TOOLS)
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    return parser.finalize()


@pytest.mark.parametrize("chunk", [1, 4, 17])
def test_valid_entml_invoke_batch_and_stream(chunk: int) -> None:
    text = f"我先读文件。\n{VALID_INVOKE}\n完成。"
    clean, calls = _parse_batch(text)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "Read"
    assert "cursor_agent_simple.py" in calls[0]["function"]["arguments"]
    assert "entml:invoke" not in clean

    clean_s, calls_s = _parse_stream(text, chunk=chunk)
    assert len(calls_s) == 1
    assert calls_s[0]["function"]["name"] == "Read"
    assert "entml:invoke" not in clean_s


def test_wrong_json_object_not_parsed_as_tool() -> None:
    text = f"调用工具：\n{WRONG_JSON_TOOL}"
    clean, calls = _parse_batch(text)
    assert calls == []
    assert "Read" in clean or "name" in clean


def test_wrong_tool_block_not_parsed_as_entml_invoke() -> None:
    text = f"回复\n{WRONG_TOOL_BLOCK}"
    clean, calls = _parse_batch(text)
    assert calls == []


def test_truncated_json_not_parsed() -> None:
    clean, calls = _parse_batch(FAKE_PARTIAL_JSON)
    assert calls == []


def test_thinking_then_valid_invoke(chunk: int = 5) -> None:
    text = (
        "<entml:thinking>\n需要先读脚本\n</entml:thinking>\n"
        f"{VALID_INVOKE}"
    )
    clean, calls = _parse_stream(text, chunk=chunk)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "Read"


def test_fault_thinking_close_then_invoke() -> None:
    text = (
        "<entml:thinking>\nplan\n</thinking>\n"
        '<entml:invoke name="get_time">\n'
        "</entml:invoke>"
    )
    clean, calls = _parse_stream(text, chunk=2)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_time"
    assert json.loads(calls[0]["function"]["arguments"]) == {}


def test_invoke_inside_unclosed_thinking_not_parsed_as_tool() -> None:
    text = f"<entml:thinking>\nplan {VALID_INVOKE}\n"
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    for i in range(0, len(text), 4):
        parser.feed(text[i : i + 4])
    assert not parser.has_calls
    clean, calls = parser.finalize()
    assert len(calls) == 0
    assert VALID_INVOKE in parser.partial_thinking


def test_multiline_parameter_preserved() -> None:
    body = "line1\nline2\nline3"
    text = (
        '<entml:invoke name="Read">\n'
        f'<entml:parameter name="path">{body}</entml:parameter>\n'
        "</entml:invoke>"
    )
    _, calls = _parse_batch(text)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["path"] == body
