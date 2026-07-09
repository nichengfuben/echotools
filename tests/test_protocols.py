from __future__ import annotations

from echotools.fncall import get_protocol, inject_fncall


def test_entml_protocol_parse() -> None:
    """entml 协议解析工具调用。"""
    proto = get_protocol("entml")
    text = (
        '<entml:function_calls><entml:invoke name="f">'
        '<entml:parameters>{"x":1}</entml:parameters></entml:invoke></entml:function_calls>'
    )
    clean, calls = proto.parse(text)
    assert calls
    assert calls[0]["function"]["name"] == "f"


def test_inject_no_tools() -> None:
    """无工具时原样返回。"""
    proto = get_protocol("entml")
    msgs = [{"role": "user", "content": "hi"}]
    assert inject_fncall(msgs, [], proto) == msgs
