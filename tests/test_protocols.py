from __future__ import annotations

from echotools.fncall import get_protocol, inject_fncall


def test_xml_protocol_parse() -> None:
    """xml 协议解析工具调用。"""
    proto = get_protocol("antml")
    text = (
        '<function_calls><invoke name="f">'
        '<parameters>{"x":1}</parameters></invoke></function_calls>'
    )
    clean, calls = proto.parse(text)
    assert calls
    assert calls[0]["function"]["name"] == "f"


def test_inject_no_tools() -> None:
    """无工具时原样返回。"""
    proto = get_protocol("xml")
    msgs = [{"role": "user", "content": "hi"}]
    assert inject_fncall(msgs, [], proto) == msgs
