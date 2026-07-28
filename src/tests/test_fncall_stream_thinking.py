from __future__ import annotations

import pytest

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


def test_invoke_inside_unclosed_thinking_not_parsed_as_tool() -> None:
    """未闭合 thinking 内的 invoke 一律视为思考正文，不解析为工具。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    stream = f"<entml:thinking>\nplan {INVOKE}\n"
    for i in range(0, len(stream), 7):
        parser.feed(stream[i : i + 7])
    assert not parser.has_calls
    assert "plan" in parser.partial_thinking
    clean, calls = parser.finalize()
    assert len(calls) == 0
    assert INVOKE in parser.partial_thinking


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


def test_stream_thinking_invoke_inside_stays_in_thinking_until_close() -> None:
    """thinking 未闭合时 invoke 留在思考链；闭合后 invoke 若在块外才解析。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    parser.feed("<entml:thinking>\n")
    parser.feed("line one\n")
    assert "line one" in parser.partial_thinking
    assert not parser.has_calls
    parser.feed(f"mention {INVOKE}\n")
    assert not parser.has_calls
    parser.feed(f"</entml:thinking>\n{INVOKE}\nanswer")
    assert parser.has_calls
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert "answer" in clean


@pytest.mark.parametrize("chunk", [1, 5, 8, 17])
def test_fault_thinking_close_then_invoke(chunk: int) -> None:
    """``</thinking>`` 后若出现 invoke，则在该处结束思考并解析工具。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<entml:thinking>\nplan\n</thinking>\n{INVOKE}"
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    clean, calls = parser.finalize()
    assert "plan" in parser.partial_thinking
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert "Hangzhou" in calls[0]["function"]["arguments"]
    assert INVOKE not in clean


@pytest.mark.parametrize("chunk", [8, 17])
def test_fault_close_multiline_parameter_not_empty_args(chunk: int) -> None:
    """``</thinking>`` 后 invoke/parameter 之间有换行时，分片不应丢 ``<ent`` 前缀。"""
    read_invoke = (
        '<entml:invoke name="Read">\n'
        '<entml:parameter name="path">C:/tmp/x.py</entml:parameter>\n'
        "</entml:invoke>"
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[
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
        },
    ])
    text = f"<entml:thinking>\nplan\n</thinking>\n{read_invoke}"
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    _, calls = parser.finalize()
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "Read"
    assert "C:/tmp/x.py" in calls[0]["function"]["arguments"]
    assert calls[0]["function"]["arguments"] != "{}"


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


def test_orphan_thinking_close_without_open_stays_visible() -> None:
    """无 ``<entml:thinking>`` 开标签时不应把正文重分类为 thinking。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = "plan step one\nplan step two\n</entml:thinking>\nvisible reply\n"
    for i in range(0, len(text), 9):
        parser.feed(text[i : i + 9])
    assert "plan step one" in parser.partial_text
    assert "plan step one" not in parser.partial_thinking
    assert "visible reply" in parser.partial_text


def test_todolist_array_param_streams_as_json_array_not_string() -> None:
    """array 参数在 partial_json 中必须是 JSON 数组，而非字符串。"""
    import json

    todo_tools = [
        {
            "type": "function",
            "function": {
                "name": "TodoList",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "status": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["todos"],
                },
            },
        },
    ]
    todos_json = '[{"title": "测试 Bash 工具", "status": "in_progress"}]'
    text = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        '<entml:invoke name="TodoList">\n'
        f'<entml:parameter name="todos">{todos_json}</entml:parameter>\n'
        "</entml:invoke>"
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=todo_tools)
    merged = ""
    for i in range(0, len(text), 5):
        parser.feed(text[i : i + 5])
        d = parser.consume_stream_delta()
        if d:
            merged += d[1]
    parsed = json.loads(merged)
    assert isinstance(parsed["todos"], list)
    assert parsed["todos"][0]["title"] == "测试 Bash 工具"
    _, calls = parser.finalize()
    assert json.loads(calls[0]["function"]["arguments"]) == parsed


def test_prose_invoke_mention_preserved_in_visible_text() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = "当我使用`<entml:invoke>`格式时，参数要简单。\n"
    parser.feed(text)
    clean, calls = parser.finalize()
    assert not calls
    assert "<entml:invoke>" in parser.partial_text
    assert "<entml:invoke>" in clean


def test_prose_invoke_mention_preserved_in_thinking_stream() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = "<entml:thinking>\n当我使用`<entml:invoke>`格式时\n</entml:thinking>\n"
    for i in range(0, len(text), 4):
        parser.feed(text[i : i + 4])
    _, calls = parser.finalize()
    assert not calls
    assert "<entml:invoke>" in parser.partial_thinking


def test_stream_delta_not_emitted_for_invoke_inside_unclosed_thinking() -> None:
    """未闭合 thinking 内的 invoke 不应产生 tool_calls 流式 delta。"""
    bash_tools = [
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
    ]
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=bash_tools)
    text = (
        "<entml:thinking>\nneed to run echo\n"
        '<entml:invoke name="Bash">\n'
        '<entml:parameter name="command">echo hello</entml:parameter>\n'
        "</entml:invoke>\n"
    )
    merged = ""
    for ch in text:
        parser.feed(ch)
        delta = parser.consume_stream_delta()
        if delta:
            merged += delta[1]
    assert merged == ""
    assert not parser.has_calls
    _, calls = parser.finalize()
    assert len(calls) == 0


def test_fault_thinking_close_stays_open_while_waiting_for_invoke() -> None:
    filt = EntmlThinkingStreamFilter()
    filt.feed("<entml:thinking>\nplan\n</thinking>\nstill ")
    assert filt.in_open_thinking()
    filt.feed("waiting\n")
    assert filt.in_open_thinking()
    filt.feed(INVOKE)
    kinds = [k for k, _ in filt.feed("")]
    assert "content" in kinds or filt.in_open_thinking() is False


def test_plain_thinking_open_then_invoke_stream() -> None:
    """plain ``<thinking>`` 开标签 + ``</thinking>`` 闭合后应能解析工具。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<thinking>\nplan\n</thinking>\n{INVOKE}"
    for i in range(0, len(text), 7):
        parser.feed(text[i : i + 7])
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "get_weather"
    assert "plan" in parser.partial_thinking
    assert "Hangzhou" in clean or len(calls) == 1


def test_plain_thinking_open_entml_close_then_invoke() -> None:
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<thinking>\nplan\n</entml:thinking>\n{INVOKE}"
    parser.feed(text)
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert "plan" in parser.partial_thinking


def test_entml_open_fault_close_then_invoke_still_works(chunk: int = 3) -> None:
    """``<entml:thinking>`` + ``</thinking>`` + 工具：fault 闭合。"""
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=TOOLS)
    text = f"<entml:thinking>\nplan\n</thinking>\n{INVOKE}"
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert "plan" in parser.partial_thinking


@pytest.mark.parametrize("chunk", [1, 5, 17])
def test_thinking_disabled_plain_open_stays_visible(chunk: int) -> None:
    """未开思考时 plain ``<thinking>`` 不得进入思考链。"""
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=TOOLS,
        protocol_options={"thinking_mode": "off"},
    )
    text = "<thinking>\nplan\n</thinking>\nvisible\n"
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    clean, calls = parser.finalize()
    assert not calls
    assert not parser.partial_thinking
    assert "<thinking>" in parser.partial_text or "plan" in parser.partial_text
    assert "visible" in clean


def test_thinking_disabled_fault_close_not_applied() -> None:
    """未开思考时 ``</thinking>`` 不得作为 entml 块的 fault 闭合。"""
    parser = FncallStreamParser(
        protocol=get_protocol("entml"),
        tools=TOOLS,
        protocol_options={"thinking_mode": "off"},
    )
    text = f"<entml:thinking>\nplan\n</thinking>\n{INVOKE}"
    parser.feed(text)
    clean, calls = parser.finalize()
    assert len(calls) == 1
    assert "plan" not in parser.partial_thinking or "</thinking>" in parser.partial_thinking
