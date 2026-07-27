from __future__ import annotations

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_think.parse import (
    EntmlThinkingStreamFilter,
    has_unclosed_entml_thinking,
    split_entml_thinking,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

INVOKE = (
    '<entml:invoke name="get_weather">'
    '<entml:parameter name="city">Hangzhou</entml:parameter>'
    "</entml:invoke>"
)


def test_has_unclosed_entml_thinking() -> None:
    assert not has_unclosed_entml_thinking("")
    assert not has_unclosed_entml_thinking("hello")
    assert has_unclosed_entml_thinking("<entml:thinking>\nstep")
    assert has_unclosed_entml_thinking("<entml:thinking>\nstep</entml:think")
    assert not has_unclosed_entml_thinking(
        "<entml:thinking>\nstep\n</entml:thinking>\nanswer"
    )


def test_in_open_thinking_hold_open_tag() -> None:
    filt = EntmlThinkingStreamFilter()
    assert not filt.in_open_thinking()
    filt.feed("prefix <entml:think")
    assert filt.in_open_thinking()


def test_split_entml_thinking_ignores_unclosed_block() -> None:
    text = "<entml:thinking>still going\n" + INVOKE
    content, thinking = split_entml_thinking(text)
    assert thinking == ""
    assert INVOKE in content


def test_invoke_inside_unclosed_thinking_not_parsed() -> None:
    """未闭合 thinking 内的 entml 标签仅作思考文本，不解析为 tool call。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    stream = f"<entml:thinking>\nplan {INVOKE}\n"
    for i in range(0, len(stream), 7):
        parser.feed(stream[i : i + 7])
    assert not parser.has_calls
    assert INVOKE in parser.partial_thinking or "entml:invoke" in parser.partial_thinking
    clean, calls = parser.finalize()
    assert len(calls) == 0


def test_invoke_after_thinking_close_is_parsed() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<entml:thinking>ok</entml:thinking>\n\n{INVOKE}"
    parser.feed(text)
    assert parser.has_calls
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert "Hangzhou" in calls[0]["function"]["arguments"]


def test_thinking_close_and_invoke_in_one_chunk() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    chunks = ["<entml:thinking>reason</entml:thinking>", INVOKE]
    for chunk in chunks:
        parser.feed(chunk)
    clean, calls = parser.finalize()
    assert parser.partial_thinking.strip() == "reason"
    assert len(calls) == 1
    assert "reason" not in clean or clean.strip() == ""


def test_no_thinking_invoke_still_works() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    parser.feed(f"Sure.\n{INVOKE}")
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert "Sure" in clean


def test_stream_thinking_invoke_inside_stays_thinking_until_close() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    parser.feed("<entml:thinking>\n")
    parser.feed("line one\n")
    assert "line one" in parser.partial_thinking
    assert not parser.has_calls
    parser.feed(f"mention {INVOKE}\n")
    assert not parser.has_calls
    assert "entml:invoke" in parser.partial_thinking
    parser.feed("</entml:thinking>\nanswer")
    clean, calls = parser.finalize()
    assert len(calls) == 0
    assert "answer" in clean


def test_fault_thinking_close_then_invoke() -> None:
    """``</thinking>`` 后若出现 invoke，则在该处结束思考并解析工具。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<entml:thinking>\nplan\n</thinking>\n{INVOKE}"
    for i in range(0, len(text), 5):
        parser.feed(text[i : i + 5])
    clean, calls = parser.finalize()
    assert "plan" in parser.partial_thinking
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert INVOKE not in clean


def test_fault_thinking_close_without_invoke_is_plain_text() -> None:
    """``</thinking>`` 后若无 invoke 直到 ``</entml:thinking>``，则视为思考内纯文本。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = "<entml:thinking>\nplan\n</thinking>\nmore\n</entml:thinking>\nanswer"
    parser.feed(text)
    clean, calls = parser.finalize()
    assert len(calls) == 0
    assert "plan" in parser.partial_thinking
    assert "</thinking>" in parser.partial_thinking or "more" in parser.partial_thinking
    assert "answer" in clean


def test_fault_thinking_close_stays_open_while_waiting_for_invoke() -> None:
    filt = EntmlThinkingStreamFilter()
    filt.feed("<entml:thinking>\nplan\n</thinking>\nstill ")
    assert filt.in_open_thinking()
    filt.feed("waiting\n")
    assert filt.in_open_thinking()
    filt.feed(INVOKE)
    kinds = [k for k, _ in filt.feed("")]
    assert "content" in kinds or filt.in_open_thinking() is False
