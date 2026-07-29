from __future__ import annotations

"""entml 工具链路全方位边界测试：类型转换 / 解析 / 过滤 / 构建。"""

import json
from typing import Any, Dict, List, Optional

import pytest

from echotools.exec.fncall import get_protocol, inject_fncall
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml import (
    strip_entml_from_content,
)
from echotools.exec.fncall.protocols.entml_invoke import (
    format_entml_parameter_value,
    format_entml_tool_calls,
    parse_invoke_args,
)
from echotools.exec.fncall.protocols.entml_patterns import (
    extract_attr_value,
    normalize_entml_name,
    strip_tool_entml_residue,
)
from echotools.exec.fncall.protocols.entml_think.parse import split_entml_thinking
from echotools.exec.fncall.protocols.entml_schema import format_entml_tool_descs
from echotools.exec.fncall.protocols.entml_schema import (
    coerce_entml_arguments,
    coerce_entml_parameter_value,
)
from echotools.exec.fncall.shared.coercion import (
    _build_param_schema_index,
    _coerce_param_value,
)
from echotools.exec.fncall.shared.normalization import normalize_tool_call

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

RICH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "rich_tool",
            "description": "All scalar and container types.\nLine two.",
            "parameters": {
                "type": "object",
                "properties": {
                    "s": {"type": "string"},
                    "i": {"type": "integer"},
                    "n": {"type": "number"},
                    "b": {"type": "boolean"},
                    "z": {"type": "null"},
                    "arr": {"type": "array", "items": {"type": "integer"}},
                    "obj": {
                        "type": "object",
                        "properties": {
                            "k": {"type": "string"},
                            "v": {"type": "integer"},
                        },
                    },
                    "maybe": {"type": ["string", "null"]},
                    "choice": {"enum": ["a", "b", "c"]},
                    "any_num": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
                "required": ["s"],
            },
        },
    }
]

SEARCH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "filters": {"type": "object"},
                },
                "required": ["query"],
            },
        },
    }
]


def _proto():
    return get_protocol("entml")


def _parse(text: str, tools: Optional[List[Dict[str, Any]]] = None):
    return _proto().parse(text, tools or RICH_TOOLS)


def _args(calls):
    return [json.loads(c["function"]["arguments"]) for c in calls]


def _invoke(name: str, params: Dict[str, str], *, type_attrs: Optional[Dict[str, str]] = None) -> str:
    type_attrs = type_attrs or {}
    lines = [f'<entml:invoke name="{name}">']
    for key, value in params.items():
        extra = f' type="{type_attrs[key]}"' if key in type_attrs else ""
        lines.append(f'<entml:parameter name="{key}"{extra}>{value}</entml:parameter>')
    lines.append("</entml:invoke>")
    return "\n".join(lines)


# ===========================================================================
# 1) 参数类型转换
# ===========================================================================


class TestCoercionUnit:
    @pytest.mark.parametrize(
        "raw,schema,expected",
        [
            ("hello", {"type": "string"}, "hello"),
            ("  hello  ", {"type": "string"}, "hello"),  # strip 后保留正文
            ("42", {"type": "string"}, "42"),
            ("true", {"type": "string"}, "true"),  # 勿把 JSON bool 字面量变成 "True"
            ('{"a":1}', {"type": "string"}, '{"a":1}'),
            ('"quoted"', {"type": "string"}, "quoted"),  # JSON 字符串字面量解包
            ("7", {"type": "integer"}, 7),
            ("7.0", {"type": "integer"}, 7),
            ("  8  ", {"type": "integer"}, 8),
            ("3.14", {"type": "integer"}, 3.14),  # 非整浮点保留 float
            ("x", {"type": "integer"}, "x"),
            ("3.5", {"type": "number"}, 3.5),
            ("9", {"type": "number"}, 9),
            ("true", {"type": "boolean"}, True),
            ("false", {"type": "boolean"}, False),
            ("yes", {"type": "boolean"}, True),
            ("no", {"type": "boolean"}, False),
            ("1", {"type": "boolean"}, True),
            ("0", {"type": "boolean"}, False),
            ("on", {"type": "boolean"}, True),
            ("off", {"type": "boolean"}, False),
            ("TRUE", {"type": "boolean"}, True),
            ("maybe", {"type": "boolean"}, "maybe"),
            ("null", {"type": "null"}, None),
            ('[1,2]', {"type": "array", "items": {"type": "integer"}}, [1, 2]),
            (
                '["1","2"]',
                {"type": "array", "items": {"type": "integer"}},
                [1, 2],
            ),
            ("not-list", {"type": "array", "items": {}}, "not-list"),
            (
                '{"k":"x","v":"3"}',
                {
                    "type": "object",
                    "properties": {
                        "k": {"type": "string"},
                        "v": {"type": "integer"},
                    },
                },
                {"k": "x", "v": 3},
            ),
            ("a", {"enum": ["a", "b"]}, "a"),
            ("5", {"anyOf": [{"type": "integer"}, {"type": "null"}]}, 5),
            ("", {"type": "string"}, ""),
        ],
    )
    def test_coerce_param_value_schema(self, raw, schema, expected) -> None:
        assert _coerce_param_value(raw, schema) == expected

    @pytest.mark.parametrize(
        "raw,hint,expected",
        [
            ("42", "int", 42),
            ("42", "integer", 42),
            ("3.2", "float", 3.2),
            ("3.2", "number", 3.2),
            ("3.2", "double", 3.2),
            ("true", "bool", True),
            ("false", "boolean", False),
            ("hi", "str", "hi"),
            ("hi", "string", "hi"),
            ('[1,2]', "array", [1, 2]),
            ('[1,2]', "list", [1, 2]),
            ('{"a":1}', "object", {"a": 1}),
            ('{"a":1}', "dict", {"a": 1}),
            ("42", "unknown_hint", "42"),  # 未知 hint 退回默认 str
        ],
    )
    def test_coerce_by_type_hint(self, raw, hint, expected) -> None:
        assert coerce_entml_parameter_value(raw, type_hint=hint) == expected

    def test_type_hint_overrides_tool_schema(self) -> None:
        # 模型 parameter type 优先于工具 schema
        assert (
            coerce_entml_parameter_value(
                "42",
                schema={"type": "string"},
                type_hint="int",
            )
            == 42
        )
        assert (
            coerce_entml_parameter_value(
                "3",
                schema={"type": "integer"},
                type_hint="str",
            )
            == "3"
        )

    def test_default_no_schema_keeps_scalars_as_str(self) -> None:
        assert coerce_entml_parameter_value("42") == "42"
        assert coerce_entml_parameter_value("true") == "true"
        assert coerce_entml_parameter_value("") == ""
        assert coerce_entml_parameter_value("  ") == ""

    def test_default_auto_json_for_containers(self) -> None:
        assert coerce_entml_parameter_value('[1, "a"]') == [1, "a"]
        assert coerce_entml_parameter_value('{"x": true}') == {"x": True}
        assert coerce_entml_parameter_value("{bad") == "{bad"
        assert coerce_entml_parameter_value("[bad") == "[bad"

    def test_coerce_arguments_dict_with_schema_index(self) -> None:
        index = _build_param_schema_index(RICH_TOOLS)
        out = coerce_entml_arguments(
            {"s": "ok", "i": "9", "b": "true", "arr": "[1,2]", "unknown": "keep"},
            "rich_tool",
            index,
        )
        assert out == {
            "s": "ok",
            "i": 9,
            "b": True,
            "arr": [1, 2],
            "unknown": "keep",
        }

    def test_coerce_arguments_skips_non_string_values(self) -> None:
        index = _build_param_schema_index(RICH_TOOLS)
        out = coerce_entml_arguments(
            {"i": 3, "b": False},
            "rich_tool",
            index,
        )
        assert out == {"i": 3, "b": False}

    def test_coerce_arguments_mangled_extra_fields_use_schema(self) -> None:
        from echotools.exec.fncall.protocols.entml_schema import _coerce_entml_arg_value

        index = _build_param_schema_index(RICH_TOOLS)
        out = coerce_entml_arguments(
            {"i": 30, "s": "echo hi"},
            "rich_tool",
            index,
        )
        assert out["i"] == 30
        assert isinstance(out["i"], int)
        assert _coerce_entml_arg_value(30, {"type": "integer"}) == 30


# ===========================================================================
# 2) 解析机制边界
# ===========================================================================


class TestParseBoundaries:
    def test_multi_invoke_order_preserved(self) -> None:
        text = (
            _invoke("rich_tool", {"s": "a", "i": "1"})
            + "\n"
            + _invoke("rich_tool", {"s": "b", "i": "2"})
        )
        clean, calls = _parse(text)
        assert clean == ""
        assert [c["function"]["name"] for c in calls] == ["rich_tool", "rich_tool"]
        assert _args(calls) == [{"s": "a", "i": 1}, {"s": "b", "i": 2}]

    def test_parameter_whitespace_and_multiline(self) -> None:
        text = (
            '<entml:invoke name="rich_tool">'
            '<entml:parameter name="s">\n  line1\n  line2  \n</entml:parameter>'
            "</entml:invoke>"
        )
        _, calls = _parse(text)
        # 仅 strip 首尾空白，保留内部换行与缩进
        assert _args(calls)[0]["s"] == "line1\n  line2"

    def test_parameter_value_with_angle_brackets(self) -> None:
        text = _invoke("rich_tool", {"s": "a <b> & c"})
        _, calls = _parse(text)
        assert _args(calls)[0]["s"] == "a <b> & c"

    def test_parameters_json_block_preferred(self) -> None:
        text = (
            '<entml:invoke name="rich_tool">'
            '<entml:parameters>{"s":"from-json","i":4}</entml:parameters>'
            '<entml:parameter name="s">ignored</entml:parameter>'
            "</entml:invoke>"
        )
        _, calls = _parse(text)
        assert _args(calls)[0] == {"s": "from-json", "i": 4}

    def test_parameters_invalid_json_falls_back_to_sub_tags(self) -> None:
        text = (
            '<entml:invoke name="search">'
            "<entml:parameters>"
            "<query>hello</query><limit>3</limit>"
            "</entml:parameters>"
            "</entml:invoke>"
        )
        _, calls = _proto().parse(text, SEARCH_TOOLS)
        assert _args(calls)[0] == {"query": "hello", "limit": 3}

    def test_parameters_invalid_json_no_subtags_becomes_value(self) -> None:
        text = (
            '<entml:invoke name="rich_tool">'
            "<entml:parameters>not-json-and-no-tags</entml:parameters>"
            "</entml:invoke>"
        )
        _, calls = _parse(text)
        assert _args(calls)[0] == {"value": "not-json-and-no-tags"}

    def test_missing_name_attribute_skipped(self) -> None:
        text = (
            '<entml:invoke>'
            '<entml:parameter name="s">x</entml:parameter>'
            "</entml:invoke>"
            + _invoke("rich_tool", {"s": "ok"})
        )
        _, calls = _parse(text)
        assert len(calls) == 1
        assert _args(calls)[0]["s"] == "ok"

    def test_parameter_without_name_skipped(self) -> None:
        text = (
            '<entml:invoke name="rich_tool">'
            "<entml:parameter>no-name</entml:parameter>"
            '<entml:parameter name="s">keep</entml:parameter>'
            "</entml:invoke>"
        )
        _, calls = _parse(text)
        assert _args(calls)[0] == {"s": "keep"}

    def test_empty_invoke_body(self) -> None:
        text = '<entml:invoke name="rich_tool"></entml:invoke>'
        _, calls = _parse(text)
        assert _args(calls)[0] == {}

    def test_unclosed_invoke_not_parsed(self) -> None:
        text = '<entml:invoke name="rich_tool"><entml:parameter name="s">x</entml:parameter>'
        clean, calls = _parse(text)
        assert calls == []
        # 开标签残留应被过滤掉
        assert "entml:invoke" not in clean

    def test_type_attr_aliases_without_schema(self) -> None:
        text = (
            '<entml:invoke name="echo">'
            '<entml:parameter name="a" type="int">1</entml:parameter>'
            '<entml:parameter name="b" type="bool">yes</entml:parameter>'
            '<entml:parameter name="c" type="list">[1,2]</entml:parameter>'
            '<entml:parameter name="d" type="dict">{"x":1}</entml:parameter>'
            "</entml:invoke>"
        )
        _, calls = _proto().parse(text, None)
        assert _args(calls)[0] == {"a": 1, "b": True, "c": [1, 2], "d": {"x": 1}}

    def test_type_before_name_and_spaces_in_attrs(self) -> None:
        assert extract_attr_value('  name = "rich_tool" ') == "rich_tool"
        assert extract_attr_value(' type = "str" name = "s" ', "name") == "s"
        assert extract_attr_value(' type = "str" name = "s" ', "type") == "str"
        _, calls = _parse(
            '<entml:invoke name="rich_tool">'
            '<entml:parameter type = "str" name = "s">hi</entml:parameter>'
            "</entml:invoke>"
        )
        assert _args(calls)[0]["s"] == "hi"

    def test_name_normalization_markdown_escapes(self) -> None:
        assert normalize_entml_name("get\\_weather") == "get_weather"
        assert normalize_entml_name("a\\-b") == "a-b"
        text = (
            '<entml:invoke name="rich\\_tool">'
            '<entml:parameter name="s">x</entml:parameter>'
            "</entml:invoke>"
        )
        _, calls = _parse(text)
        assert calls[0]["function"]["name"] == "rich_tool"

    def test_text_before_and_after_invoke(self) -> None:
        text = "前言\n" + _invoke("rich_tool", {"s": "x"}) + "\n后记"
        clean, calls = _parse(text)
        assert _args(calls)[0]["s"] == "x"
        assert "前言" in clean and "后记" in clean
        assert "entml:" not in clean

    def test_wrapper_and_thinking_together(self) -> None:
        text = (
            "<entml:thinking>plan</entml:thinking>\n"
            "答：\n"
            "<entml:function_calls>\n"
            + _invoke("rich_tool", {"s": "x", "i": "2"})
            + "\n</entml:function_calls>"
        )
        clean, calls = _parse(text)
        assert _args(calls)[0] == {"s": "x", "i": 2}
        assert clean == "答："
        _, thinking = split_entml_thinking(text)
        assert thinking == "plan"
        assert "entml:" not in clean

    def test_parse_invoke_args_direct(self) -> None:
        index = _build_param_schema_index(RICH_TOOLS)
        body = (
            '<entml:parameter name="s">t</entml:parameter>'
            '<entml:parameter name="b">false</entml:parameter>'
        )
        assert parse_invoke_args(body, "rich_tool", index) == {"s": "t", "b": False}

    def test_normalize_tool_call_python_list_literal(self) -> None:
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
            "id": "c1",
            "type": "function",
            "function": {
                "name": "run",
                "arguments": json.dumps({"items": "['a', 'b']"}),
            },
        }
        out = normalize_tool_call(tc, tools)
        assert json.loads(out["function"]["arguments"])["items"] == ["a", "b"]


# ===========================================================================
# 3) 过滤机制
# ===========================================================================


class TestFilterMechanisms:
    def test_strip_tool_residue_keeps_thinking_and_modes(self) -> None:
        raw = (
            "<entml:thinking>secret</entml:thinking>\n"
            "<entml:thinking_mode>on</entml:thinking_mode>\n"
            "<entml:max_thinking_length>100</entml:max_thinking_length>\n"
            "<entml:function_calls>"
            '<entml:invoke name="rich_tool">'
            '<entml:parameter name="s">x</entml:parameter>'
            "</entml:invoke></entml:function_calls>\n"
            "可见正文"
        )
        cleaned = strip_tool_entml_residue(raw)
        assert "secret" in cleaned
        assert "<entml:thinking>" in cleaned
        assert "<entml:thinking_mode>on</entml:thinking_mode>" in cleaned
        assert "<entml:max_thinking_length>100</entml:max_thinking_length>" in cleaned
        assert "可见正文" in cleaned
        assert "function_calls" not in cleaned
        assert "invoke" not in cleaned

    def test_strip_entml_from_content_strips_namespace_only(self) -> None:
        raw = (
            "A\n"
            "<entml:thinking>t</entml:thinking>\n"
            "<entml:thinking_mode>on</entml:thinking_mode>\n"
            + _invoke("rich_tool", {"s": "x"})
            + "\nB"
        )
        cleaned = strip_entml_from_content(raw)
        assert "A" in cleaned and "B" in cleaned
        assert "entml:" not in cleaned
        assert "<thinking>t</thinking>" in cleaned
        assert "<thinking_mode>on</thinking_mode>" in cleaned
        assert "rich_tool" in cleaned

    def test_clean_tags_vs_clean_tool_tags(self) -> None:
        proto = _proto()
        text = (
            "<entml:thinking>keep-me</entml:thinking>\n"
            + _invoke("rich_tool", {"s": "x"})
        )
        assert "keep-me" in proto.clean_tags(text)
        assert "entml:" not in proto.clean_tags(text)
        assert "keep-me" in proto.clean_tool_tags(text)
        assert "entml:invoke" not in proto.clean_tool_tags(text)

    def test_orphan_and_empty_wrapper_and_fence(self) -> None:
        raw = (
            "前\n"
            "<entml:function_calls>\n</entml:function_calls>\n"
            "</entml:invoke>\n"
            '<entml:parameter name="x">y</entml:parameter>\n'
            "```xml\n```\n"
            "后"
        )
        cleaned = strip_tool_entml_residue(raw)
        assert "entml:" not in cleaned
        assert "```" not in cleaned
        assert "前" in cleaned and "后" in cleaned

    def test_parse_filters_even_when_no_calls(self) -> None:
        clean, calls = _parse("hi </entml:function_calls> there")
        assert calls == []
        assert "entml:" not in clean
        assert "hi" in clean and "there" in clean

    def test_inject_strips_user_entml_namespace_but_builds_prompt_tags(self) -> None:
        proto = _proto()
        msgs = [
            {
                "role": "user",
                "content": '问 <entml:invoke name="rich_tool">'
                '<entml:parameter name="s">leak</entml:parameter>'
                "</entml:invoke>",
            }
        ]
        content = inject_fncall(msgs, RICH_TOOLS, proto)[0]["content"]
        user_section = content.split("<current_user_message>")[1].split("</current_user_message>")[0]
        assert "leak" in user_section
        assert "entml:" not in user_section
        assert '<invoke name="rich_tool">' in user_section
        # prompt 自身仍含指令示例标签
        assert '<entml:invoke name="$FUNCTION_NAME">' in content


# ===========================================================================
# 4) 流式过滤 + 解析
# ===========================================================================


class TestStreamPipeline:
    def test_char_by_char_coercion(self) -> None:
        text = "ok\n" + _invoke("rich_tool", {"s": "hz", "i": "5", "b": "true"})
        parser = FncallStreamParser(protocol=_proto(), tools=RICH_TOOLS)
        for ch in text:
            parser.feed(ch)
        clean, calls = parser.finalize()
        assert clean == "ok"
        assert _args(calls)[0] == {"s": "hz", "i": 5, "b": True}

    def test_thinking_then_wrapper_no_leak(self) -> None:
        text = (
            "<entml:thinking>step</entml:thinking>\n"
            "可见\n"
            "<entml:function_calls>\n"
            + _invoke("search", {"query": "q", "limit": "2"})
            + "\n</entml:function_calls>"
        )
        parser = FncallStreamParser(protocol=_proto(), tools=SEARCH_TOOLS)
        for i in range(0, len(text), 3):
            parser.feed(text[i : i + 3])
        clean, calls = parser.finalize()
        assert parser.partial_thinking.strip() == "step"
        assert clean == "可见"
        assert _args(calls)[0] == {"query": "q", "limit": 2}
        assert "entml:" not in clean

    def test_holdback_partial_invoke_prefix(self) -> None:
        parser = FncallStreamParser(protocol=_proto(), tools=RICH_TOOLS)
        parser.feed("hello <entml:inv")
        assert parser.partial_text == "hello "
        assert not parser.has_calls
        parser.feed('oke name="rich_tool"><entml:parameter name="s">x</entml:parameter></entml:invoke>')
        clean, calls = parser.finalize()
        assert clean == "hello"
        assert _args(calls)[0]["s"] == "x"

    def test_wrapper_without_invoke_name_not_detected(self) -> None:
        parser = FncallStreamParser(protocol=_proto(), tools=RICH_TOOLS)
        parser.feed("前文\n<entml:function_calls>\n")
        assert parser.partial_text == "前文\n"
        assert not parser.has_calls
        parser.feed('<entml:invoke name="rich_tool">')
        assert parser.has_calls
        assert parser.partial_text == "前文"
        parser.feed(
            '<entml:parameter name="s">x</entml:parameter></entml:invoke>\n'
            "</entml:function_calls>"
        )
        clean, calls = parser.finalize()
        assert clean == "前文"
        assert _args(calls)[0]["s"] == "x"

    def test_prose_before_invoke_name_line_streams_after_stable(self) -> None:
        parser = FncallStreamParser(protocol=_proto(), tools=RICH_TOOLS)
        parser.feed("明白，不用 <tool> 块。现在用 `\n")
        assert not parser.has_calls
        assert "<tool>" in parser.partial_text
        parser.feed('<entml:invoke name="rich_tool">')
        assert parser.has_calls
        assert "entml:" not in parser.partial_text
        ready = parser.feed(
            '<entml:parameter name="s">ok</entml:parameter></entml:invoke>'
        )
        assert len(ready) == 1
        assert ready[0]["function"]["name"] == "rich_tool"

    def test_finalize_idempotent(self) -> None:
        parser = FncallStreamParser(protocol=_proto(), tools=RICH_TOOLS)
        parser.feed(_invoke("rich_tool", {"s": "x"}))
        a = parser.finalize()
        b = parser.finalize()
        assert a == b


# ===========================================================================
# 5) 构建机制
# ===========================================================================


class TestBuildMechanisms:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, "null"),
            (True, "true"),
            (False, "false"),
            (3, "3"),
            (1.5, "1.5"),
            ("hi", "hi"),
            ([1, "a"], '[1, "a"]'),
            ({"k": 1}, '{"k": 1}'),
        ],
    )
    def test_format_parameter_value(self, value, expected) -> None:
        assert format_entml_parameter_value(value) == expected

    def test_format_tool_calls_roundtrip_with_schema(self) -> None:
        calls = [
            {
                "id": "call_0000",
                "type": "function",
                "function": {
                    "name": "rich_tool",
                    "arguments": json.dumps(
                        {
                            "s": "hello",
                            "i": 3,
                            "b": False,
                            "arr": [1, 2],
                            "obj": {"k": "v", "v": 9},
                            "z": None,
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ]
        rendered = format_entml_tool_calls(calls)
        assert '<entml:parameter name="s">hello</entml:parameter>' in rendered
        assert '<entml:parameter name="i">3</entml:parameter>' in rendered
        assert '<entml:parameter name="b">false</entml:parameter>' in rendered
        assert '<entml:parameter name="z">null</entml:parameter>' in rendered
        assert "function_calls" not in rendered  # 裸 invoke 格式

        clean, parsed = _parse(rendered)
        assert clean == ""
        args = _args(parsed)[0]
        assert args["s"] == "hello"
        assert args["i"] == 3
        assert args["b"] is False
        assert args["arr"] == [1, 2]
        assert args["obj"] == {"k": "v", "v": 9}
        assert args["z"] is None

    def test_format_empty_tool_calls(self) -> None:
        assert format_entml_tool_calls([]) == ""

    def test_format_tool_descs_structure(self) -> None:
        out = format_entml_tool_descs(RICH_TOOLS)
        assert "### rich_tool" in out
        assert (
            "Description:\nAll scalar and container types.\nLine two."
        ) in out
        assert '"properties"' in out
        assert out.index('"properties"') < out.index('"type"')
        assert "```json" in out

    def test_assistant_history_tool_turn_block(self) -> None:
        proto = _proto()
        tool_calls = [
            {
                "id": "c1",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"query": "西湖", "limit": 2}),
                },
            },
            {
                "id": "c2",
                "type": "function",
                "function": {
                    "name": "search",
                    "arguments": json.dumps({"query": "灵隐"}),
                },
            },
        ]
        block = proto.format_assistant_tool_turn_block(
            tool_calls,
            {
                "c1": {"content": "结果A"},
                "c2": {"content": "结果B"},
            },
        )
        assert block.startswith("<tool>")
        assert '{search: {"query": "西湖", "limit": 2}}' in block
        assert "{search: 灵隐}" in block
        assert "结果A" in block and "结果B" in block
        assert "→ Result:" not in block

    def test_format_assistant_tool_calls_compact_lines(self) -> None:
        proto = _proto()
        lines = proto.format_assistant_tool_calls(
            [
                {
                    "id": "1",
                    "type": "function",
                    "function": {
                        "name": "rich_tool",
                        "arguments": json.dumps({"s": "x", "arr": [1, 2]}),
                    },
                }
            ]
        )
        assert lines == '{rich_tool: {"s": "x", "arr": [1, 2]}}'

    def test_render_prompt_section_order(self) -> None:
        proto = _proto()
        prompt = proto.render_prompt(
            tool_descs=proto.format_tool_descs(SEARCH_TOOLS),
            lang="en",
            user_system_prompt="sys",
            history_text="<user>\nhi\n</user>",
            loop_warning="loop!",
            current_user_message="now",
            protocol_options={"thinking_mode": "on", "max_thinking_length": 100},
            history_has_tool_calls=True,
        )
        idx_tools = prompt.index("### search")
        idx_sys = prompt.index("<user_system_prompt>")
        idx_hist = prompt.index("<entml:conversation_history>")
        idx_loop = prompt.index("<loop_warning>")
        idx_user = prompt.index("<current_user_message>")
        idx_remind = prompt.index("IMPORTANT: If you execute a tool in this turn")
        idx_think = prompt.index("<entml:thinking_mode>")
        assert idx_tools < idx_sys < idx_hist < idx_loop < idx_user < idx_remind < idx_think

    def test_inject_builds_history_tool_blocks(self) -> None:
        proto = _proto()
        msgs = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "calling",
                "tool_calls": [
                    {
                        "id": "t1",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": json.dumps({"query": "q"}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "found"},
            {"role": "user", "content": "next"},
        ]
        content = inject_fncall(msgs, SEARCH_TOOLS, proto)[0]["content"]
        assert "<tool>" in content
        assert "{search: q}" in content
        assert "found" in content
        assert "<current_user_message>\nnext\n</current_user_message>" in content
        assert "IMPORTANT: If you execute a tool in this turn" in content

    def test_build_then_parse_multi_tool_roundtrip(self) -> None:
        rendered = format_entml_tool_calls(
            [
                {
                    "id": "1",
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": json.dumps(
                            {"query": "a", "limit": 1, "tags": ["x"]}
                        ),
                    },
                },
                {
                    "id": "2",
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": json.dumps({"query": "b", "filters": {"lang": "zh"}}),
                    },
                },
            ]
        )
        clean, calls = _proto().parse(rendered, SEARCH_TOOLS)
        assert clean == ""
        assert _args(calls) == [
            {"query": "a", "limit": 1, "tags": ["x"]},
            {"query": "b", "filters": {"lang": "zh"}},
        ]


# ===========================================================================
# 6) 端到端：构建 → 流式解析 → 类型转换 → 过滤
# ===========================================================================


class TestEndToEnd:
    def test_full_pipeline(self) -> None:
        proto = _proto()
        # 构建上游会看到的模型输出形态
        model_out = (
            "<entml:thinking>先搜再总结</entml:thinking>\n"
            "正在检索。\n"
            "<entml:function_calls>\n"
            + format_entml_tool_calls(
                [
                    {
                        "id": "c0",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": json.dumps(
                                {"query": "杭州", "limit": 3, "tags": ["a", "b"]}
                            ),
                        },
                    }
                ]
            )
            + "\n</entml:function_calls>"
        )
        parser = FncallStreamParser(protocol=proto, tools=SEARCH_TOOLS)
        for i in range(0, len(model_out), 11):
            parser.feed(model_out[i : i + 11])
        clean, calls = parser.finalize()
        display, thinking = split_entml_thinking(clean)
        assert thinking == "先搜再总结" or "先搜再总结" in parser.partial_thinking
        assert "正在检索。" in (display or clean)
        assert "entml:" not in (display or "")
        assert len(calls) == 1
        assert json.loads(calls[0]["function"]["arguments"]) == {
            "query": "杭州",
            "limit": 3,
            "tags": ["a", "b"],
        }
