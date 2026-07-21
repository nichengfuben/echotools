from __future__ import annotations

import json

import pytest

from echotools.exec.fncall import get_protocol, inject_fncall, list_protocols
from echotools.exec.fncall.shared.normalization import normalize_tool_call


@pytest.mark.parametrize(
    "protocol_id,sample,expected_name",
    [
        (
            "entml",
            '<entml:function_calls><entml:invoke name="tool_a">'
            '<entml:parameters>{"x":1}</entml:parameters></entml:invoke></entml:function_calls>',
            "tool_a",
        ),
        (
            "entml",
            '<entml:function_calls><entml:invoke name="tool_x">'
            '<entml:parameter name="x">1</entml:parameter></entml:invoke></entml:function_calls>',
            "tool_x",
        ),
    ],
)
def test_protocol_parse(protocol_id: str, sample: str, expected_name: str) -> None:
    proto = get_protocol(protocol_id)
    _, calls = proto.parse(sample)
    assert calls
    assert calls[0]["function"]["name"] == expected_name


def test_list_protocols_includes_builtins() -> None:
    assert list_protocols() == ["entml"]


def test_custom_protocol_requires_plugin() -> None:
    with pytest.raises(ValueError, match="Provider-Fncall-Util"):
        get_protocol("custom", custom_prompt_en="Use tools")


def test_get_protocol_platform_mapping() -> None:
    proto = get_protocol(platform_id="p1", mapping={"p1": "entml"})
    assert proto.id == "entml"


def test_normalize_tool_call_python_literal() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "run",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        }
    ]
    tc = {
        "id": "call_0001",
        "type": "function",
        "function": {
            "name": "run",
            "arguments": json.dumps({"items": "['a', 'b']"}),
        },
    }
    out = normalize_tool_call(tc, tools)
    args = json.loads(out["function"]["arguments"])
    assert args["items"] == ["a", "b"]


def test_inject_with_tools_and_dump(tmp_path) -> None:
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    msgs = [{"role": "user", "content": "find cats"}]
    out = inject_fncall(
        msgs,
        tools,
        proto,
        dump_prompt=True,
        dump_dir=str(tmp_path),
    )
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert list(tmp_path.glob("*.txt"))
