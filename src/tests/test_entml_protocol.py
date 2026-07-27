from __future__ import annotations

import json

import pytest

from echotools.exec.fncall import get_protocol, inject_fncall
from echotools.exec.fncall.protocols.entml_invoke import parse_entml_tool_calls
from echotools.exec.fncall.protocols.entml_thinking import (
    build_entml_thinking_section,
    normalize_thinking_mode,
)
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
    assert "<current_user_message>\nhi\n</current_user_message>" in content
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
            "thinking_mode": "on",
            "max_thinking_length": 22000,
        },
    )[0]["content"]
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in with_opts
    assert "<entml:max_thinking_length>22000</entml:max_thinking_length>" in with_opts
    assert "MUST output a thinking block" in with_opts
    assert "At the very start of your response" in with_opts


def test_build_entml_thinking_section_empty_without_options() -> None:
    assert build_entml_thinking_section(None) == ""
    assert build_entml_thinking_section({}) == ""


def test_parse_max_thinking_length() -> None:
    from echotools.exec.fncall.protocols.entml_thinking import parse_max_thinking_length

    assert parse_max_thinking_length(None) is None
    assert parse_max_thinking_length("") is None
    assert parse_max_thinking_length("  ") is None
    assert parse_max_thinking_length(0) is None
    assert parse_max_thinking_length(22000) == 22000
    assert parse_max_thinking_length("22000") == 22000


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("off", "off"),
        ("disabled", "off"),
        ("on", "on"),
        ("enabled", "on"),
        ("interleaved", "auto"),
        ("auto", "auto"),
        ("adaptive", "auto"),
        ("bogus", None),
    ],
)
def test_normalize_thinking_mode(raw, expected) -> None:
    assert normalize_thinking_mode(raw) == expected


def test_thinking_prompt_off() -> None:
    assert build_entml_thinking_section({"thinking_mode": "off"}) == ""
    assert build_entml_thinking_section(
        {"thinking_mode": "off", "max_thinking_length": 22000}
    ) == ""


def test_thinking_prompt_on_without_max_length() -> None:
    section = build_entml_thinking_section({"thinking_mode": "on"})
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in section
    assert "<entml:max_thinking_length>" not in section


def test_thinking_prompt_on() -> None:
    section = build_entml_thinking_section({"thinking_mode": "on"})
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in section
    assert "forced thinking" in section
    assert "MUST output a thinking block" in section
    assert "<entml:thinking>" in section
    assert "`<entml:invoke>`" in section
    assert "<entml:function_calls>" not in section
    assert "You must NOT output any thinking blocks" not in section


def test_thinking_prompt_auto() -> None:
    section = build_entml_thinking_section({"thinking_mode": "auto"})
    assert "<entml:thinking_mode>auto</entml:thinking_mode>" in section
    assert "model decides" in section
    assert "<tool>" in section
    assert "[tool_name: value ]" in section
    assert "→ Result:" not in section
    assert "[tool_name(" not in section
    assert "<function_results>" not in section
    assert "<entml:function_calls>" not in section
    assert "strongly prefer to output one if you are uncertain" in section
    assert "MUST output a thinking block" not in section


def test_inject_no_tools_with_thinking_off() -> None:
    proto = get_protocol("entml")
    msgs = [{"role": "user", "content": "hi"}]
    result = inject_fncall(
        msgs,
        [],
        proto,
        protocol_options={"thinking_mode": "off"},
    )[0]["content"]
    assert "<entml:thinking_mode>" not in result
    assert "<entml:max_thinking_length>" not in result
    assert "You must NOT output any thinking blocks" not in result
    assert "<current_user_message>\nhi\n</current_user_message>" in result


def test_inject_no_tools_with_thinking_on() -> None:
    proto = get_protocol("entml")
    msgs = [{"role": "user", "content": "hi"}]
    result = inject_fncall(
        msgs,
        [],
        proto,
        protocol_options={"thinking_mode": "on"},
    )[0]["content"]
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in result
    assert "MUST output a thinking block" in result


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
    assert "<current_user_message>\nnew\n</current_user_message>" in content


def test_entml_history_clarify_always_english() -> None:
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
    content = inject_fncall(msgs, tools, proto, lang="zh")[0]["content"]
    assert "The following is a transcript of completed interactions." in content
    assert "以下是已完成的交互记录" not in content
    assert "Reminder — tool notation in the conversation history above" not in content


def test_entml_history_tool_invoke_reminder_when_tools_in_history() -> None:
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]
    msgs = [
        {"role": "user", "content": "find docs"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"query": "docs"}),
                },
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "found 3"},
        {"role": "user", "content": "summarize"},
    ]
    content = inject_fncall(msgs, tools, proto)[0]["content"]
    assert "[search: docs ]" in content
    assert "<tool>" in content
    assert "found 3" in content
    assert "IMPORTANT: Completed tool turns in conversation history" in content
    assert "`<entml:invoke>` block" in content
    hist_idx = content.index("<entml:conversation_history>")
    reminder_idx = content.index("IMPORTANT: Completed tool turns")
    user_idx = content.index("<current_user_message>")
    assert hist_idx < reminder_idx < user_idx


def test_entml_multi_tool_history_blocks() -> None:
    """同一 assistant 轮次并行多工具时，每个调用独立 <tool> 块。"""
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Query local time",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Web search",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
    ]
    msgs = [
        {"role": "user", "content": "plan trip"},
        {
            "role": "assistant",
            "content": "checking time and attractions",
            "tool_calls": [
                {
                    "id": "call_t1",
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "arguments": json.dumps({"city": "Hangzhou"}),
                    },
                },
                {
                    "id": "call_s1",
                    "type": "function",
                    "function": {
                        "name": "search_web",
                        "arguments": json.dumps({"query": "West Lake spots"}),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_t1",
            "content": "2026-07-26 14:30 CST",
        },
        {
            "role": "tool",
            "tool_call_id": "call_s1",
            "content": "Broken Bridge, Leifeng Pagoda",
        },
        {"role": "user", "content": "summarize"},
    ]
    content = inject_fncall(msgs, tools, proto)[0]["content"]

    hist_start = content.index("<entml:conversation_history>")
    hist_end = content.index("</entml:conversation_history>")
    history = content[hist_start:hist_end]

    assert history.count("<tool>") == 2
    assert history.count("</tool>") == 2
    assert "[get_time: Hangzhou ]" in history
    assert "[search_web: West Lake spots ]" in history
    assert "2026-07-26 14:30 CST" in history
    assert "Broken Bridge, Leifeng Pagoda" in history
    assert "→ Result:" not in history
    assert "[get_time(" not in history
    assert "[search_web(" not in history

    time_block = (
        "<tool>\n[get_time: Hangzhou ]\n2026-07-26 14:30 CST\n</tool>"
    )
    search_block = (
        "<tool>\n[search_web: West Lake spots ]\n"
        "Broken Bridge, Leifeng Pagoda\n</tool>"
    )
    assert time_block in history
    assert search_block in history


@pytest.mark.parametrize(
    "raw,schema,expected",
    [
        ("true", {"type": "boolean"}, True),
        ("false", {"type": "boolean"}, False),
        ("42", {"type": "integer"}, 42),
        ("3.14", {"type": "number"}, 3.14),
        ("null", None, "null"),
        ('["a","b"]', {"type": "array", "items": {"type": "string"}}, ["a", "b"]),
        ('["a","b"]', None, ["a", "b"]),
        ("plain text", {"type": "string"}, "plain text"),
        ("plain text", None, "plain text"),
        ("42", None, "42"),
        ("42", "int", 42),
        ("true", None, "true"),
        ("true", "bool", True),
    ],
)
def test_coerce_entml_parameter_value(raw, schema, expected) -> None:
    if isinstance(schema, str):
        assert coerce_entml_parameter_value(raw, type_hint=schema) == expected
    else:
        assert coerce_entml_parameter_value(raw, schema) == expected


def test_entml_instruction_matches_spec_format() -> None:
    """示范格式：```text 调用示例 + ### 工具名 + 外置 Description + parameters-only JSON。"""
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ask_user_input_v0",
                "description": "Ask user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["question"],
                },
            },
        }
    ]
    prompt = proto.render_prompt(
        tool_descs=proto.format_tool_descs(tools),
        lang="en",
        current_user_message="pick one",
        protocol_options={
            "thinking_mode": "on",
            "max_thinking_length": 22000,
        },
    )
    assert "In this environment you have access to a set of tools" in prompt
    assert "Here are the functions available in JSONSchema format:" in prompt
    assert "```text" in prompt
    assert "### ask_user_input_v0" in prompt
    assert "**ask_user_input_v0**" not in prompt
    assert 'Description: "Ask user"' in prompt
    assert '"name": "ask_user_input_v0"' not in prompt
    assert "<entml:function_calls>" not in prompt
    assert '<entml:invoke name="$FUNCTION_NAME">' in prompt
    assert '<entml:parameter name="$PARAMETER_NAME">' in prompt
    assert "String and scalar parameters should be specified as is" in prompt
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in prompt
    assert "<entml:max_thinking_length>22000</entml:max_thinking_length>" in prompt
    assert "MUST output a thinking block" in prompt
    assert "<function_results>" not in prompt
    assert "<entml:conversation_history>" not in prompt
    assert "<entml:history>" not in prompt
    assert "<functions>" not in prompt


def test_entml_roundtrip_parameter_format() -> None:
    """渲染与解析均使用 <entml:parameter name=\"...\">。"""
    from echotools.exec.fncall.protocols.entml_invoke import format_entml_tool_calls

    sample_calls = [
        {
            "id": "call_0000",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": json.dumps(
                    {"query": "hello", "limit": 3, "tags": ["a", "b"]}
                ),
            },
        }
    ]
    rendered = format_entml_tool_calls(sample_calls)
    assert '<entml:parameter name="query">hello</entml:parameter>' in rendered
    assert '<entml:parameter name="limit">3</entml:parameter>' in rendered
    assert '<entml:parameter name="tags">["a", "b"]</entml:parameter>' in rendered
    assert "<parameter name=" not in rendered

    parsed = parse_entml_tool_calls(rendered, None, None)
    args = json.loads(parsed[0]["function"]["arguments"])
    assert args["query"] == "hello"
    assert args["limit"] == "3"
    assert args["tags"] == ["a", "b"]


def test_entml_parse_parameter_type_attribute() -> None:
    """模型可能在 parameter 标签上附带 type 属性（如 type=\"str\"）。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "units": {"type": "string"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        },
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:function_calls>'
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city" type="str">Shanghai</entml:parameter>'
        '<entml:parameter name="units" type="str">celsius</entml:parameter>'
        "</entml:invoke>"
        '<entml:invoke name="search_web">'
        '<entml:parameter name="query" type="str">上海 明天 降雨 2026-07-23</entml:parameter>'
        '<entml:parameter name="limit" type="int">3</entml:parameter>'
        "</entml:invoke>"
        "</entml:function_calls>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    assert len(calls) == 2

    weather = json.loads(calls[0]["function"]["arguments"])
    assert weather == {"city": "Shanghai", "units": "celsius"}

    search = json.loads(calls[1]["function"]["arguments"])
    assert search["query"] == "上海 明天 降雨 2026-07-23"
    assert search["limit"] == 3
    assert isinstance(search["limit"], int)


def test_entml_parse_parameter_default_str_without_type_attr() -> None:
    """无 type= 且无 schema 时，标量默认按 str 处理。"""
    sample = (
        '<entml:function_calls><entml:invoke name="echo">'
        '<entml:parameter name="count">42</entml:parameter>'
        '<entml:parameter name="flag">true</entml:parameter>'
        "</entml:invoke></entml:function_calls>"
    )
    calls = parse_entml_tool_calls(sample, None, None)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {"count": "42", "flag": "true"}


def test_entml_parse_parameter_type_hint_without_schema() -> None:
    sample = (
        '<entml:function_calls><entml:invoke name="echo">'
        '<entml:parameter name="count" type="int">42</entml:parameter>'
        '<entml:parameter name="flag" type="bool">true</entml:parameter>'
        "</entml:invoke></entml:function_calls>"
    )
    calls = parse_entml_tool_calls(sample, None, None)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {"count": 42, "flag": True}


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


def test_inject_include_thinking_in_history() -> None:
    """protocol_options.include_thinking_in_history 应在历史中渲染 entml:thinking。"""
    proto = get_protocol("entml")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    msgs = [
        {"role": "user", "content": "查北京天气"},
        {
            "role": "assistant",
            "reasoning": "应先调用 get_weather 获取实时数据。",
            "content": "我来查一下。",
        },
        {"role": "user", "content": "那上海呢？"},
    ]
    plain = inject_fncall(msgs, tools, proto)[0]["content"]
    assert "应先调用 get_weather" not in plain

    with_history = inject_fncall(
        msgs,
        tools,
        proto,
        protocol_options={"include_thinking_in_history": True},
    )[0]["content"]
    assert "<entml:thinking>" in with_history
    assert "应先调用 get_weather 获取实时数据。" in with_history
    assert "那上海呢？" in with_history
