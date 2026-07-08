from __future__ import annotations

import pytest

from echotools.fncall import get_protocol, inject_fncall, list_protocols


@pytest.mark.parametrize(
    "protocol_id,sample,expected_name",
    [
        (
            "antml",
            '<antml:function_calls><antml:invoke name="tool_a">'
            '<antml:parameters>{"x":1}</antml:parameters></antml:invoke></antml:function_calls>',
            "tool_a",
        ),
        (
            "xml",
            '<function_calls><invoke name="tool_x">'
            '<parameter name="x">1</parameter></invoke></function_calls>',
            "tool_x",
        ),
        (
            "bracket",
            "[function_calls][call:tool_b]{\"y\":2}[/call][/function_calls]",
            "tool_b",
        ),
    ],
)
def test_protocol_parse(protocol_id: str, sample: str, expected_name: str) -> None:
    proto = get_protocol(protocol_id)
    _, calls = proto.parse(sample)
    assert calls
    assert calls[0]["function"]["name"] == expected_name


def test_list_protocols_includes_builtins() -> None:
    ids = list_protocols()
    for expected in ("xml", "antml", "original", "bracket", "nous", "dsml"):
        assert expected in ids


def test_custom_protocol_lazy_create() -> None:
    proto = get_protocol("custom", custom_prompt_en="Use tools")
    assert proto.id == "custom"


def test_get_protocol_platform_mapping() -> None:
    proto = get_protocol(platform_id="p1", mapping={"p1": "xml"})
    assert proto.id == "xml"


def test_inject_with_tools_and_dump(tmp_path) -> None:
    proto = get_protocol("xml")
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
