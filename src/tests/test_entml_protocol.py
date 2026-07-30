from __future__ import annotations

import json

import pytest

from echotools.exec.fncall import get_protocol, inject_fncall
from echotools.exec.fncall.protocols.entml_invoke import parse_entml_tool_calls
from echotools.exec.fncall.protocols.entml_patterns import (
    invoke_structural_gap_text,
    invoke_structural_gaps,
    parameter_block_spans,
)
from echotools.exec.fncall.protocols.entml_schema import coerce_entml_parameter_value
from echotools.exec.fncall.protocols.entml_think.core import (
    build_entml_thinking_section,
    default_max_thinking_length_for_level,
    normalize_thinking_level,
    normalize_thinking_mode,
    resolve_thinking_injection,
)
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
    assert "<thinking_behavior>" in with_opts
    assert "Every reply begins with a thinking block" in with_opts
    assert "A tool invocation never appears inside the thinking block" in with_opts


def test_build_entml_thinking_section_empty_without_options() -> None:
    assert build_entml_thinking_section(None) == ""
    assert build_entml_thinking_section({}) == ""


def test_parse_max_thinking_length() -> None:
    from echotools.exec.fncall.protocols.entml_think.core import (
        parse_max_thinking_length,
    )

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
        ("none", "off"),
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


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("none", "none"),
        ("off", "none"),
        ("low", "low"),
        ("medium", "medium"),
        ("med", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("max", "max"),
        ("auto", "auto"),
        ("interleaved", "auto"),
        ("bogus", None),
    ],
)
def test_normalize_thinking_level(raw, expected) -> None:
    assert normalize_thinking_level(raw) == expected


@pytest.mark.parametrize(
    "level,expected",
    [
        ("low", 12800),
        ("medium", 25600),
        ("high", 64000),
        ("xhigh", 102400),
        ("max", 134736),
        ("none", None),
        ("auto", None),
    ],
)
def test_default_max_thinking_length_for_level(level, expected) -> None:
    assert default_max_thinking_length_for_level(level) == expected


def test_resolve_thinking_injection_levels() -> None:
    assert resolve_thinking_injection({"thinking_level": "none"}) is None
    assert resolve_thinking_injection({"thinking_level": "low"}) == ("low", 12800)
    assert resolve_thinking_injection({"thinking_level": "high"}) == ("high", 64000)
    assert resolve_thinking_injection({"thinking_level": "auto"}) == ("auto", None)
    assert resolve_thinking_injection({
        "thinking_level": "max",
        "max_thinking_length": 1000,
    }) == ("max", 1000)


def test_thinking_prompt_off() -> None:
    assert build_entml_thinking_section({"thinking_mode": "off"}) == ""
    assert build_entml_thinking_section({"thinking_level": "none"}) == ""
    assert build_entml_thinking_section(
        {"thinking_mode": "off", "max_thinking_length": 22000}
    ) == ""


def test_thinking_prompt_off_with_history_thinking_injects_no_think_behavior() -> None:
    history = (
        "<user>\nfirst\n</user>\n"
        "<assistant>\n<entml:thinking>\nplan\n</entml:thinking>\nok\n</assistant>"
    )
    section = build_entml_thinking_section(
        {"thinking_mode": "off"},
        history_text=history,
    )
    assert "<entml:thinking_mode>" not in section
    assert "<thinking_behavior>" in section
    assert "Do NOT output a <entml:thinking> block" in section
    assert "Do not imitate or continue those blocks" in section


def test_thinking_prompt_off_without_history_thinking_stays_empty() -> None:
    history = "<user>\nfirst\n</user>\n<assistant>\nok\n</assistant>"
    assert build_entml_thinking_section(
        {"thinking_mode": "off"},
        history_text=history,
    ) == ""


def test_thinking_prompt_off_history_thinking_no_tools() -> None:
    history = "<assistant>\n<entml:thinking>\np\n</entml:thinking>\nhi\n</assistant>"
    section = build_entml_thinking_section(
        {"thinking_level": "none"},
        has_tools=False,
        history_text=history,
    )
    assert "<thinking_behavior>" in section
    assert "Extended thinking is disabled" in section
    assert "<entml:invoke>" not in section


def test_thinking_prompt_on_without_max_length() -> None:
    section = build_entml_thinking_section({"thinking_mode": "on"})
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in section
    assert "<entml:max_thinking_length>25600</entml:max_thinking_length>" in section
    assert "<thinking_behavior>" in section


def test_thinking_prompt_on_by_level() -> None:
    section = build_entml_thinking_section({"thinking_level": "low"})
    assert "<entml:thinking_mode>low</entml:thinking_mode>" in section
    assert "<entml:max_thinking_length>12800</entml:max_thinking_length>" in section
    assert "Every reply begins with a thinking block" in section


def test_thinking_prompt_medium_by_level() -> None:
    section = build_entml_thinking_section({"thinking_level": "medium"})
    assert "<entml:thinking_mode>medium</entml:thinking_mode>" in section
    assert "<entml:max_thinking_length>25600</entml:max_thinking_length>" in section


def test_thinking_prompt_on() -> None:
    section = build_entml_thinking_section({"thinking_mode": "on"})
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in section
    assert "<thinking_behavior>" in section
    assert section.index("<thinking_behavior>") < section.index(
        "<entml:max_thinking_length>"
    )
    assert section.index("<entml:max_thinking_length>") < section.index(
        "<entml:thinking_mode>"
    )
    assert "Every reply begins with a thinking block" in section
    assert "Simplified Chinese" in section
    assert "`<entml:invoke>`" not in section
    assert "<entml:function_calls>" not in section


def test_thinking_prompt_on_no_tools() -> None:
    section = build_entml_thinking_section({"thinking_mode": "on"}, has_tools=False)
    assert "Every reply begins with a thinking block" in section
    assert "<entml:invoke>" not in section


def test_thinking_prompt_auto_no_tools() -> None:
    section = build_entml_thinking_section({"thinking_level": "auto"}, has_tools=False)
    assert "Every reply begins with a thinking block" in section
    assert "<tool>" not in section


def test_thinking_prompt_auto() -> None:
    section = build_entml_thinking_section({"thinking_level": "auto"})
    assert "<entml:thinking_mode>auto</entml:thinking_mode>" in section
    assert "<entml:max_thinking_length>" not in section
    assert "<thinking_behavior>" in section
    assert "Every reply begins with a thinking block" in section
    assert "<tool>" not in section


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
    assert "<thinking_behavior>" in result
    assert "Every reply begins with a thinking block" in result
    assert "<entml:invoke>" not in result
    idx_behavior = result.index("<thinking_behavior>")
    idx_user = result.index("</current_user_message>")
    idx_mode = result.index("<entml:thinking_mode>")
    assert idx_behavior < idx_user < idx_mode


def test_inject_thinking_off_history_with_entml_thinking_injects_no_think_behavior() -> None:
    proto = get_protocol("entml")
    tools = [
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
    msgs = [
        {"role": "user", "content": "查北京"},
        {
            "role": "assistant",
            "reasoning": "先查天气。",
            "content": "好的。",
        },
        {"role": "user", "content": "那上海呢？"},
    ]
    prompt = inject_fncall(
        msgs,
        tools,
        proto,
        protocol_options={
            "thinking_mode": "off",
            "include_thinking_in_history": True,
        },
    )[0]["content"]
    assert "<entml:conversation_history>" in prompt
    assert "<entml:thinking>" in prompt.split("<current_user_message>")[0]
    assert "<entml:thinking_mode>" not in prompt
    assert "<thinking_behavior>" in prompt
    assert "Do NOT output a <entml:thinking> block" in prompt
    assert prompt.rstrip().endswith("</current_user_message>")


def test_inject_thinking_off_history_without_entml_thinking_unchanged() -> None:
    proto = get_protocol("entml")
    tools = [
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
    msgs = [
        {"role": "user", "content": "查北京"},
        {"role": "assistant", "content": "好的。"},
        {"role": "user", "content": "那上海呢？"},
    ]
    prompt = inject_fncall(
        msgs,
        tools,
        proto,
        protocol_options={"thinking_mode": "off"},
    )[0]["content"]
    assert "<entml:thinking_mode>" not in prompt
    assert "<thinking_behavior>" not in prompt


def test_render_prompt_thinking_after_current_user() -> None:
    proto = get_protocol("entml")
    prompt = proto.render_prompt(
        tool_descs=proto.format_tool_descs([
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]),
        lang="en",
        history_text="<user>\nold\n</user>",
        current_user_message="new",
        protocol_options={"thinking_mode": "on", "max_thinking_length": 1000},
    )
    assert prompt.index("In this environment") < prompt.index("<entml:conversation_history>\n")
    idx_hist = prompt.index("<entml:conversation_history>\n")
    idx_fc = prompt.index("<function_calling_behavior>\n")
    idx_behavior = prompt.index("<thinking_behavior>\n")
    idx_hard = prompt.index("<entml:hard_constraint_restatement>\n")
    idx_user = prompt.index("<current_user_message>\n")
    idx_max = prompt.index("<entml:max_thinking_length>")
    idx_mode = prompt.index("<entml:thinking_mode>")
    assert idx_hist < idx_fc < idx_behavior < idx_hard < idx_user < idx_max < idx_mode
    assert prompt.rstrip().endswith("</entml:thinking_mode>")


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


def test_inject_no_current_user_when_last_is_assistant() -> None:
    """末条非 user 时：用户消息进 history，不构建 <current_user_message>。"""
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
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "partial reply"},
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": "still composing"},
    ]
    content = inject_fncall(msgs, tools, proto)[0]["content"]
    assert "<entml:conversation_history>" in content
    assert "<user>\nfollow up\n</user>" in content
    assert "<assistant>\nstill composing\n</assistant>" in content
    assert "<current_user_message>" not in content


def test_inject_thinking_after_history_when_no_current_user() -> None:
    proto = get_protocol("entml")
    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    content = inject_fncall(
        msgs, [], proto, protocol_options={"thinking_mode": "on"},
    )[0]["content"]
    assert "<current_user_message>" not in content
    assert content.index("<entml:conversation_history>") < content.index(
        "<entml:thinking_mode>"
    )


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
    assert "transcript of completed interactions" in content
    assert "id-comment format shown below" in content
    assert "must not repeat a tool call using the same tool and the same parameters" in content
    assert "The user's latest message follows below." in content
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
    content = inject_fncall(
        msgs, tools, proto, protocol_options={"thinking_level": "high"},
    )[0]["content"]
    assert '<entml:invoke name="search">' in content
    assert '"query": "docs"' in content or "docs" in content
    assert "<!-- Tool Result ID:call_1 -->" in content
    assert '<entml:result id="call_1">' in content
    assert "found 3" in content
    assert "<entml:funtions_results>" in content
    assert "<function_calling_behavior>" in content
    assert "IMPORTANT: The <entml:funtions_results> block is a top-level block" in content
    hist_idx = content.index("<entml:conversation_history>\n")
    results_idx = content.index("<entml:funtions_results>\n")
    fc_idx = content.index("<function_calling_behavior>\n")
    behavior_idx = content.index("<thinking_behavior>\n")
    hard_idx = content.index("<entml:hard_constraint_restatement>\n")
    user_idx = content.index("<current_user_message>\n")
    assert hist_idx < results_idx < fc_idx < behavior_idx < hard_idx < user_idx


def test_strip_entml_from_user_content() -> None:
    from echotools.exec.fncall.protocols.entml import strip_entml_from_content

    raw = (
        "请查天气\n"
        "<entml:thinking>thinking body</entml:thinking>\n"
        '<entml:invoke name="get_weather">'
        '<entml:parameter name="city">杭州</entml:parameter>'
        "</entml:invoke>"
    )
    cleaned = strip_entml_from_content(raw)
    assert cleaned == (
        "请查天气\n"
        "<thinking>thinking body</thinking>\n"
        '<invoke name="get_weather">'
        '<parameter name="city">杭州</parameter>'
        "</invoke>"
    )
    assert "entml:" not in cleaned
    assert "thinking body" in cleaned
    assert "杭州" in cleaned
    assert cleaned.count("//") == raw.count("//")


def test_strip_entml_from_user_preserves_double_slash() -> None:
    from echotools.exec.fncall.protocols.entml import strip_entml_from_content

    raw = '<entml:invoke name="x">//path//</entml:invoke>'
    assert strip_entml_from_content(raw) == '<invoke name="x">//path//</invoke>'


def test_inject_strips_entml_from_all_user_messages() -> None:
    proto = get_protocol("entml")
    msgs = [
        {
            "role": "user",
            "content": (
                "历史问题 <entml:thinking>secret</entml:thinking> 继续"
            ),
        },
        {"role": "assistant", "content": "ok"},
        {
            "role": "user",
            "content": (
                '当前问题 <entml:invoke name="search">'
                '<entml:parameter name="q">x</entml:parameter>'
                "</entml:invoke> 结束"
            ),
        },
    ]
    content = inject_fncall(msgs, [], proto)[0]["content"]
    assert "secret" in content or "<thinking>secret</thinking>" in content
    assert "entml:invoke" not in content
    assert '<invoke name="search">' in content or "search" in content
    assert "历史问题" in content and "继续" in content
    assert "当前问题" in content and "结束" in content
    assert "<current_user_message>" in content


def test_entml_multi_tool_history_blocks() -> None:
    """同一 assistant 轮次并行多工具时，invoke/result 内联于 assistant 块。"""
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

    hist_start = content.index("<entml:conversation_history>\n")
    hist_end = content.index("</entml:conversation_history>")
    history = content[hist_start:hist_end]

    assert '<entml:invoke name="get_time">' in history
    assert '<entml:invoke name="search_web">' in history
    assert history.count("<!-- Tool Result ID:") == 2
    assert history.count("<entml:result>") == 0
    assert "<tool>" not in history
    assert "<assistant>" in history
    assert "checking time and attractions" in history
    assert "2026-07-26 14:30 CST" not in history
    assert "Broken Bridge, Leifeng Pagoda" not in history

    results_start = content.index("<entml:funtions_results>\n")
    results_end = content.index("</entml:funtions_results>")
    results = content[results_start:results_end]
    assert "2026-07-26 14:30 CST" in results
    assert "Broken Bridge, Leifeng Pagoda" in results
    assert results.count('<entml:result id="') == 2
    assert "→ Result:" not in history
    assert "[get_time(" not in history
    assert "[search_web(" not in history


def test_entml_history_multiline_tool_uses_json_object() -> None:
    """多行参数写入 history 时用 entml:invoke + entml:parameter。"""
    proto = get_protocol("entml")
    contents = 'print("hello")\nline2'
    args = {"file_path": "x.py", "contents": contents}
    block = proto.format_assistant_tool_turn_block(
        [
            {
                "id": "call_w1",
                "type": "function",
                "function": {
                    "name": "Write",
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        ],
        {},
    )
    assert '<entml:invoke name="Write">' in block
    assert '<entml:parameter name="file_path">x.py</entml:parameter>' in block
    assert "[Write:" not in block


def test_entml_history_bash_multi_param_json_braces() -> None:
    """多参数 Bash：{Bash: {\"command\": ..., \"description\": ...}}。"""
    proto = get_protocol("entml")
    args = {
        "command": "grep -oP 'https?://' /tmp/x.js | head -30",
        "description": "Find URLs",
    }
    block = proto.format_assistant_tool_turn_block(
        [
            {
                "id": "call_b1",
                "type": "function",
                "function": {
                    "name": "Bash",
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        ],
        {},
    )
    assert '<entml:invoke name="Bash">' in block
    assert '<entml:parameter name="command">' in block
    assert "[Bash:" not in block


def test_entml_history_simple_glob_stays_scalar_braces() -> None:
    """单行简单参数：{Glob: pattern}。"""
    proto = get_protocol("entml")
    block = proto.format_assistant_tool_turn_block(
        [
            {
                "id": "call_g1",
                "type": "function",
                "function": {
                    "name": "Glob",
                    "arguments": json.dumps({"pattern": "**/cursor"}),
                },
            }
        ],
        {},
    )
    assert '<entml:invoke name="Glob">' in block
    assert "**/cursor" in block


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
    """示范格式：裸 invoke 示例 + ### 工具名 + 外置 Description + parameters-only JSON。"""
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
    assert 'writing a "<entml:invoke>" block like the following' in prompt
    assert "Here are the functions available in JSONSchema format:" in prompt
    assert "```text" not in prompt
    assert "### ask_user_input_v0" in prompt
    assert "**ask_user_input_v0**" not in prompt
    assert "Description:\nAsk user" in prompt
    assert '"name": "ask_user_input_v0"' not in prompt
    assert "<entml:function_calls>" not in prompt
    assert '<entml:invoke name="$FUNCTION_NAME">' in prompt
    assert '<entml:parameter name="$PARAMETER_NAME">' in prompt
    assert "String and scalar parameters should be specified as is" in prompt
    assert "<entml:thinking_mode>on</entml:thinking_mode>" in prompt
    assert "<entml:max_thinking_length>22000</entml:max_thinking_length>" in prompt
    assert "<thinking_behavior>" in prompt
    assert "Every reply begins with a thinking block" in prompt
    assert "<function_calling_behavior>" in prompt
    assert "<function_results>" not in prompt
    assert "<entml:conversation_history>\n" not in prompt
    assert "<entml:history>" not in prompt
    assert "<functions>" not in prompt


def test_entml_prompt_and_stream_logic_no_function_calls_wrapper() -> None:
    """提示词与流式检测均不以 function_calls 为一等公民。"""
    from echotools.exec.fncall.parsers.stream import FncallStreamParser
    from echotools.exec.fncall.protocols.entml_patterns import (
        strip_legacy_function_calls_wrapper,
    )

    proto = get_protocol("entml")
    tags = proto.get_trigger_tags()
    assert "function_calls" not in " ".join(tags)

    # legacy 完整开标签在流式 normalize 时静默剥离
    stripped = strip_legacy_function_calls_wrapper(
        "前文\n<entml:function_calls>\n<entml:invoke name=\"x\">"
    )
    assert "function_calls" not in stripped
    assert stripped.startswith("前文\n<entml:invoke")

    # detect_start 只认 invoke 起点，不因 wrapper 提前切换
    found, pos = proto.detect_start(
        "<entml:function_calls>\n<entml:invoke name=\"rich_tool\">"
    )
    assert found
    assert pos == len("<entml:function_calls>\n")

    parser = FncallStreamParser(protocol=proto, tools=[])
    parser.feed("说明\n<entml:function_calls>\n")
    assert parser.partial_text == "说明\n"
    assert "function_calls" not in parser.partial_text
    parser.feed('<entml:invoke name="echo">')
    assert parser.has_calls
    parser.feed(
        '<entml:parameter name="msg">hi</entml:parameter></entml:invoke>'
        "</entml:function_calls>"
    )
    clean, calls = parser.finalize()
    assert clean == "说明"
    assert calls[0]["function"]["name"] == "echo"


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


def test_entml_parse_bare_description_timeout_tags() -> None:
    """常见 agent 风格：invoke 内裸 <entml:description>/<entml:timeout>。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "description": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:invoke name="Bash">'
        '<entml:parameter name="command" type="str">echo hi</entml:parameter>'
        "<entml:description>Run echo</entml:description>"
        "<entml:timeout>300000</entml:timeout>"
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["command"] == "echo hi"
    assert args["description"] == "Run echo"
    assert args["timeout"] == 300000


def test_entml_parse_bare_parameter_tags_in_invoke() -> None:
    """invoke 内裸 <parameter>（无 entml: 前缀），与 Edit 工具报错语料一致。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Edit",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:invoke name="Edit">'
        '<parameter name="path">X:/Project/Local/Provider-Deepseek-Adapter/main.py</parameter>'
        '<parameter name="old_string">model = "deepseek-v4-flash"</parameter>'
        '<parameter name="new_string">model = "deepseek-v4-pro"</parameter>'
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["path"] == "X:/Project/Local/Provider-Deepseek-Adapter/main.py"
    assert args["old_string"] == 'model = "deepseek-v4-flash"'
    assert args["new_string"] == 'model = "deepseek-v4-pro"'

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    for chunk in (1, 64, 9999):
        p = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
        for i in range(0, len(sample), chunk):
            p.feed(sample[i : i + chunk])
            while p.consume_stream_delta():
                pass
        p.finalize()
        stream_args = [s for s in p.stream_invoke_argument_snapshots() if s]
        assert len(stream_args) == 1, f"chunk={chunk}"
        assert json.loads(stream_args[0]) == args, f"chunk={chunk}"


def test_entml_parse_read_file_path_not_aliased() -> None:
    """Read 工具：参数名按模型输出原样保留，不做 file_path→path 映射。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Read",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "line_offset": {"type": "integer"},
                        "n_lines": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:invoke name="Read">'
        '<entml:parameter name="file_path">X:/Project/foo.py</entml:parameter>'
        '<entml:parameter name="line_offset">122</entml:parameter>'
        '<entml:parameter name="n_lines">25</entml:parameter>'
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    args = json.loads(calls[0]["function"]["arguments"])
    assert "path" not in args
    assert args["file_path"] == "X:/Project/foo.py"
    assert args["line_offset"] == 122
    assert args["n_lines"] == 25


def test_entml_parse_direct_child_tags_grep() -> None:
    """Grep 直接子元素标签（req-1785250814），非 parameter 包裹。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Grep",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                        "output_mode": {"type": "string"},
                        "-n": {"type": "boolean"},
                    },
                    "required": ["pattern"],
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        "让我用 Grep 直接确认搜索参数的传递逻辑，避免 Read 循环。\n\n"
        '<entml:invoke name="Grep">\n'
        "<pattern>search_enabled|search</pattern>\n"
        "<path>X:/Project/Local/Provider-Deepseek-Adapter/provider_deepseek/core/adapter/helpers/client_helpers.py</path>\n"
        "<output_mode>content</output_mode>\n"
        "<-n>true</-n>\n"
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {
        "pattern": "search_enabled|search",
        "path": "X:/Project/Local/Provider-Deepseek-Adapter/provider_deepseek/core/adapter/helpers/client_helpers.py",
        "output_mode": "content",
        "-n": True,
    }

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    for chunk in (1, 17, 9999):
        p = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
        for i in range(0, len(sample), chunk):
            p.feed(sample[i : i + chunk])
            while p.consume_stream_delta():
                pass
        p.finalize()
        stream_args = [s for s in p.stream_invoke_argument_snapshots() if s]
        assert len(stream_args) == 1, f"chunk={chunk}"
        assert json.loads(stream_args[0]) == args, f"chunk={chunk}"


def test_entml_stream_same_tool_name_multiple_invokes() -> None:
    """同名连续 invoke 的流式 arguments 与 batch 一致。"""
    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    tools = [
        {
            "type": "function",
            "function": {
                "name": "WebSearch",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]
    sample = (
        '<entml:invoke name="WebSearch">'
        '<entml:parameter name="query" type="str">one</entml:parameter>'
        "</entml:invoke>"
        '<entml:invoke name="WebSearch">'
        '<entml:parameter name="query" type="str">two</entml:parameter>'
        "</entml:invoke>"
        '<entml:invoke name="WebSearch">'
        '<entml:parameter name="query" type="str">three</entml:parameter>'
        "</entml:invoke>"
    )
    batch = parse_entml_tool_calls(sample, tools, _build_param_schema_index(tools))
    batch_args = [c["function"]["arguments"] for c in batch]

    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    parser.feed(sample)
    while parser.consume_stream_delta():
        pass
    parser.finalize()
    stream_args = [s for s in parser.stream_invoke_argument_snapshots() if s]
    assert stream_args == batch_args


def test_entml_parse_tool_block_inner_tags_ignored() -> None:
    """legacy ``<tool>`` 块不再解析为 tool_calls。"""
    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    tools = [
        {
            "type": "function",
            "function": {
                "name": "TodoList",
                "parameters": {
                    "type": "object",
                    "properties": {"todos": {"type": "array"}},
                    "required": ["todos"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
        },
    ]
    sample = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        "更新任务并运行测试。\n\n"
        "<tool>\n"
        "<TodoList>\n"
        '{"todos": [{"title": "task-a", "status": "done"}]}\n'
        "</tool>\n\n"
        "<tool>\n"
        "<Bash>\n"
        '{"command": "python main.py", "timeout": 120}\n'
        "</tool>"
    )
    _, batch = get_protocol("entml").parse(sample, tools)
    assert batch == []

    for chunk in (1, 17, 64):
        p = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
        for i in range(0, len(sample), chunk):
            p.feed(sample[i : i + chunk])
        stream_clean, stream_calls = p.finalize()
        assert stream_calls == [], f"chunk={chunk}"
        assert len(p.partial_thinking) > 0, f"chunk={chunk}"
        assert "更新任务" in p.partial_text or "更新任务" in stream_clean, f"chunk={chunk}"


def test_entml_tool_block_brace_skipped_when_entml_invoke_present() -> None:
    """同文含 ``<entml:invoke>`` 时，``{Edit: x}`` 伪块不解析；仅保留 invoke。"""
    tools = [
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
        {
            "type": "function",
            "function": {
                "name": "Edit",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        },
    ]
    sample = (
        "<entml:thinking>\nplan\n</entml:thinking>\n"
        "中间说明\n"
        "<tool>\n{Edit: x}\n</tool>\n"
        '<entml:invoke name="Read">\n'
        '<entml:parameter name="path">src/main.py</entml:parameter>\n'
        "</entml:invoke>\n"
        "最终回复"
    )
    clean, calls = get_protocol("entml").parse(sample, tools)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "Read"


def test_entml_stream_finalize_strips_thinking_without_tool_block_calls() -> None:
    """legacy ``<tool>`` 样本：finalize 剥离 thinking，但不解析 tool_calls。"""
    from pathlib import Path

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785255721-dc06ea92d007.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    sample = sample_path.read_text(encoding="utf-8")
    tools = [
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
        }
    ]
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    parser.feed(sample)
    clean, calls = parser.finalize()
    assert calls == []
    assert "<entml:thinking>" not in clean
    assert "StreamAiPreviews" in parser.partial_thinking
    assert len(parser.partial_thinking) > 500


def test_entml_tool_block_bash_with_output_tail_ignored() -> None:
    """legacy ``<tool>`` 块不再解析为 Bash tool_calls。"""
    from pathlib import Path

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785255721-dc06ea92d007.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    sample = sample_path.read_text(encoding="utf-8")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
        }
    ]
    _, batch_calls = get_protocol("entml").parse(sample, tools)
    assert batch_calls == []

    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    parser.feed(sample)
    _, stream_calls = parser.finalize()
    assert stream_calls == []


def test_entml_tool_block_mangled_brace_entml_params_ignored() -> None:
    """legacy ``<tool>`` 混合格式不再解析。"""
    from pathlib import Path

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785297403-7c656ac5fe40.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    sample = sample_path.read_text(encoding="utf-8")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Bash",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "description": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    "required": ["command"],
                },
            },
        }
    ]
    clean, batch_calls = get_protocol("entml").parse(sample, tools)
    assert batch_calls == []
    assert "RC4" in clean

    for chunk in (1, 17, 64):
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
        for i in range(0, len(sample), chunk):
            parser.feed(sample[i : i + chunk])
        stream_clean, stream_calls = parser.finalize()
        assert stream_calls == [], f"chunk={chunk}"
        assert len(parser.partial_thinking) > 100, f"chunk={chunk}"
        assert "RC4" in stream_clean or "RC4" in parser.partial_text, f"chunk={chunk}"


def test_entml_tool_block_brace_read_entml_params_ignored() -> None:
    """legacy ``<tool>{Read}\\n<entml:parameter>...`` 不再解析（req-1785310901）。"""
    from pathlib import Path

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785310901-34c502c9e8a9.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    sample = sample_path.read_text(encoding="utf-8")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Read",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["file_path"],
                },
            },
        }
    ]
    clean, batch_calls = get_protocol("entml").parse(sample, tools)
    assert batch_calls == []
    assert "流发送逻辑" in clean

    for chunk in (1, 17, 64):
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
        for i in range(0, len(sample), chunk):
            parser.feed(sample[i : i + chunk])
        stream_clean, stream_calls = parser.finalize()
        assert stream_calls == [], f"chunk={chunk}"
        assert "流发送逻辑" in stream_clean, f"chunk={chunk}"
        assert "流发送逻辑" not in parser.partial_thinking, f"chunk={chunk}"
        assert len(parser.partial_thinking) > 500, f"chunk={chunk}"


def test_prose_entml_invoke_mention_does_not_swallow_real_invoke() -> None:
    """正文提及 ``<entml:invoke>``（无 name）不得吞掉后续真实工具块（req-1785299710）。"""
    from pathlib import Path

    from echotools.exec.fncall.parsers.stream import FncallStreamParser

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785299710-addb90714d4d.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus sample not available")
    text = sample_path.read_text(encoding="utf-8")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "AskUserQuestion",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "header": {"type": "string"},
                                    "options": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "label": {"type": "string"},
                                                "description": {"type": "string"},
                                            },
                                        },
                                    },
                                    "multiSelect": {"type": "boolean"},
                                },
                            },
                        }
                    },
                    "required": ["questions"],
                },
            },
        }
    ]
    proto = get_protocol("entml")
    clean, batch_calls = proto.parse(text, tools)
    assert len(batch_calls) == 1
    assert batch_calls[0]["function"]["name"] == "AskUserQuestion"
    batch_args = json.loads(batch_calls[0]["function"]["arguments"])
    assert isinstance(batch_args["questions"], list)
    assert batch_args["questions"][0]["header"] == "Retest"
    assert "`<entml:invoke>`" in clean or "<entml:invoke>" in clean
    assert '<entml:invoke name="AskUserQuestion">' not in clean

    for chunk in (1, 17, 64):
        parser = FncallStreamParser(protocol=proto, tools=tools)
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
        stream_clean, stream_calls = parser.finalize()
        assert len(stream_calls) == 1, f"chunk={chunk}"
        assert json.loads(stream_calls[0]["function"]["arguments"]) == batch_args, (
            f"chunk={chunk}"
        )
        assert "`<entml:invoke>`" in stream_clean or "<entml:invoke>" in stream_clean, (
            f"chunk={chunk}"
        )


WRITE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Write",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["content"],
            },
        },
    }
]


def test_write_content_with_embedded_json_examples_not_truncated() -> None:
    """Write ``content`` 参数内嵌 JSON 示例时不得误触 mangled command 尾缀截断。"""
    from pathlib import Path

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785314805-78e418df4ea0.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    text = sample_path.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, WRITE_TOOLS)
    assert len(batch_calls) == 1
    args = json.loads(batch_calls[0]["function"]["arguments"])
    assert "thread_updated" in args["content"]
    assert "REST API" in args["content"]
    assert args["file_path"].endswith("rocket-red-tornado-damage.md")


def test_fault_thinking_close_prose_then_tool_block_ignored() -> None:
    """legacy ``<tool>{Write>`` 混合格式不再解析。"""
    from pathlib import Path

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785314760-0da55e1ba166.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    text = sample_path.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, WRITE_TOOLS)
    assert batch_calls == []


def test_write_path_content_hybrid_tool_block_ignored() -> None:
    """legacy ``<tool>{Write: ...`` 混合格式不再解析。"""
    from pathlib import Path

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785311004-438c84fa5aa4.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    text = sample_path.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, WRITE_TOOLS)
    assert batch_calls == []


def test_invoke_structural_gaps_exclude_parameter_blocks() -> None:
    body = (
        "pre\n"
        '<entml:parameter name="content"><span>x</span></entml:parameter>\n'
        "<path>src/a.py</path>\n"
        "post"
    )
    blocks = parameter_block_spans(body)
    assert len(blocks) == 1
    assert body[blocks[0][0] : blocks[0][1]].startswith("<entml:parameter")
    gaps = invoke_structural_gaps(body)
    gap_text = invoke_structural_gap_text(body)
    assert "<span>" not in gap_text
    assert "<path>src/a.py</path>" in gap_text
    assert "pre" in gap_text
    assert "post" in gap_text
    assert sum(e - s for s, e in gaps) == len(gap_text)


def test_write_parameter_payload_opaque_to_alternate_syntax() -> None:
    """parameter 块内任意类 XML/HTML 标签不得被 invoke 备用语法解析为参数。"""
    schema_index = _build_param_schema_index(WRITE_TOOLS)
    sample = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="path">src/select.js</entml:parameter>\n'
        '<entml:parameter name="content">'
        "app.component('core-collapsible', {\n"
        "  template: [\n"
        "    '<span class=\"collapsible-arrow\"></span>',\n"
        "    '<span>{{ title }}</span>',\n"
        "    '<slot></slot>',\n"
        "    '<div v-if=\"open\"></div>',\n"
        "  ].join('\\n')\n"
        "});\n"
        "</entml:parameter>\n"
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, WRITE_TOOLS, schema_index)
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert set(args.keys()) == {"file_path", "content"}
    assert "<slot></slot>" in args["content"]
    assert "{{ title }}" in args["content"]


def test_invoke_mixed_parameter_and_direct_child_syntax() -> None:
    """structural gap：parameter 与直接子标签可并存，互不污染。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Grep",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "path": {"type": "string"},
                        "-n": {"type": "boolean"},
                    },
                    "required": ["pattern"],
                },
            },
        }
    ]
    schema_index = _build_param_schema_index(tools)
    sample = (
        '<entml:invoke name="Grep">\n'
        '<entml:parameter name="pattern">foo|bar</entml:parameter>\n'
        "<path>src/main.py</path>\n"
        "<-n>true</-n>\n"
        "</entml:invoke>"
    )
    calls = parse_entml_tool_calls(sample, tools, schema_index)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {"pattern": "foo|bar", "path": "src/main.py", "-n": True}


def test_write_parameter_payload_corpus_req_1785323083() -> None:
    """回归 req-1785323083：parameter payload 内 markup 不得泄漏为额外参数。"""
    from pathlib import Path

    sample_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785323083-f6847d18c1f9.txt"
    )
    if not sample_path.is_file():
        pytest.skip("corpus file not available")
    text = sample_path.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, WRITE_TOOLS)
    write_calls = [c for c in batch_calls if c["function"]["name"] == "Write"]
    assert len(write_calls) == 1
    args = json.loads(write_calls[0]["function"]["arguments"])
    assert "span" not in args
    assert "slot" not in args
    assert args["file_path"].endswith("select.js")
    assert "core-select" in args["content"]
    assert "<slot></slot>" in args["content"]

