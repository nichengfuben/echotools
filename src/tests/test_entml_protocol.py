from __future__ import annotations

import json

import pytest

from echotools.exec.fncall import get_protocol, inject_fncall
from echotools.exec.fncall.protocols.entml_invoke import parse_entml_tool_calls
from echotools.exec.fncall.protocols.entml_thinking import build_entml_thinking_section
from echotools.exec.fncall.protocols.entml_values import coerce_entml_parameter_value
from echotools.exec.fncall.shared.coercion import _build_param_schema_index


def test_entml_protocol_parse() -> None:
    proto = get_protocol("entml")
    text = (
        '<entml:function_calls><entml:invoke name="f">'
        '<entml:parameters>{"x":1}</entml:parameters></entml:invoke></entml:function_calls>'
    )
    clean, calls = proto.parse(text)
    assert calls
    assert calls[0]["function"]["name"] == "f"


def test_inject_no_tools_entml_tags() -> None:
    proto = get_protocol("entml")
    msgs = [{"role": "user", "content": "hi"}]
    result = inject_fncall(msgs, [], proto)
    assert len(result) == 1
    content = result[0]["content"]
    assert "<entml:current_user_message>\nhi\n</entml:current_user_message>" in content
    assert "<entml:thinking_mode>" not in content
    assert "<entml:max_thinking_length>" not in content


def test_inject_with_thinking_options_only_when_declared() -> None:
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    msgs = [{"role": "user", "content": "go"}]
    plain = inject_fncall(msgs, tools, proto)[0]["content"]
    assert "<entml:thinking_mode>" not in plain

    with_opts = inject_fncall(
        msgs,
        tools,
        proto,
        protocol_options={
            "thinking_mode": "interleaved",
            "max_thinking_length": 22000,
        },
    )[0]["content"]
    assert "<entml:thinking_mode>interleaved</entml:thinking_mode>" in with_opts
    assert "<entml:max_thinking_length>22000</entml:max_thinking_length>" in with_opts
    assert "<entml:thinking>" in with_opts


def test_build_entml_thinking_section_empty_without_options() -> None:
    assert build_entml_thinking_section(None) == ""
    assert build_entml_thinking_section({}) == ""


def test_inject_with_history_entml_tags() -> None:
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    msgs = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "new"},
    ]
    out = inject_fncall(msgs, tools, proto)
    content = out[0]["content"]
    assert "<entml:conversation_history>" in content
    assert "<entml:current_user_message>\nnew\n</entml:current_user_message>" in content


@pytest.mark.parametrize(
    "raw,schema,expected",
    [
        ("true", {"type": "boolean"}, True),
        ("false", {"type": "boolean"}, False),
        ("42", {"type": "integer"}, 42),
        ("3.14", {"type": "number"}, 3.14),
        ("null", None, None),
        ('["a","b"]', {"type": "array", "items": {"type": "string"}}, ["a", "b"]),
        ("plain text", {"type": "string"}, "plain text"),
        ("plain text", None, "plain text"),
    ],
)
def test_coerce_entml_parameter_value(raw, schema, expected) -> None:
    assert coerce_entml_parameter_value(raw, schema) == expected


def test_entml_parse_schema_coercion() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "enabled": {"type": "boolean"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:function_calls><entml:invoke name="run">'
        '<entml:parameter name="count">7</entml:parameter>'
        '<entml:parameter name="enabled">true</entml:parameter>'
        '<entml:parameter name="tags">["x","y"]</entml:parameter>'
        "</entml:invoke></entml:function_calls>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {"count": 7, "enabled": True, "tags": ["x", "y"]}
