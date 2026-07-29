from __future__ import annotations

"""流式 partial_json 专项边界（语料矩阵见 test_model_branch_matrix.py）。"""

import json

import pytest
from fixtures.simulated_llm_tool_responses import TOOLS, tools_for_case
from fixtures.simulated_llm_tool_responses import (
    iter_cases_with_tools,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream_json import (
    build_streaming_json_snapshot,
    split_invoke_open,
)
from echotools.exec.fncall.shared.coercion import _build_param_schema_index

_WRITE_CASE = next(c for c in iter_cases_with_tools() if c.id == "agent_write_windows_path")


def test_force_close_matches_batch_on_truncated_invoke() -> None:
    tools = tools_for_case(_WRITE_CASE)
    text = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="file_path">C:\\Users\\partial'
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=tools)
    parser.feed(text)
    merged = ""
    delta = parser.consume_stream_delta()
    if delta:
        merged += delta[1]
    comp = parser.complete_stream_delta_if_needed()
    assert comp is not None
    merged += comp[1]
    parsed = split_invoke_open(parser._fncall_buf)
    assert parsed is not None
    name, body_start = parsed
    body = parser._fncall_buf[body_start:]
    snap = build_streaming_json_snapshot(
        body,
        tool_name=name,
        schema_index=_build_param_schema_index(tools),
        force_close=True,
    )
    assert merged == snap
    assert json.loads(merged) == {"file_path": "C:\\Users\\partial"}


def test_bare_parameter_close_at_buffer_end_snapshot() -> None:
    """裸 ``<parameter>`` 在 buffer 末尾闭合时，streaming snapshot 应视为参数已完成。"""
    from echotools.exec.fncall.protocols.entml_stream_json import (
        build_streaming_json_snapshot,
    )

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
                    },
                    "required": ["pattern"],
                },
            },
        }
    ]
    body = (
        '<parameter name="pattern">foo|bar</parameter>'
    )
    snap = build_streaming_json_snapshot(
        body,
        tool_name="Grep",
        schema_index=_build_param_schema_index(tools),
    )
    assert "</parameter>" not in snap
    assert snap == '{"pattern": "foo|bar"'
    assert json.loads(snap + "}") == {"pattern": "foo|bar"}


def test_read_anyof_integer_stream_json_buf_matches_batch() -> None:
    """Rogator Read：line_offset 为 anyOf integer 时，流式 json_buf 不得误加引号（143143）。"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "Read",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "line_offset": {
                            "anyOf": [
                                {"type": "integer", "minimum": 1},
                                {"type": "integer", "maximum": -1},
                            ],
                        },
                        "n_lines": {"type": "integer", "exclusiveMinimum": 0},
                    },
                    "required": ["path"],
                },
            },
        }
    ]
    text = (
        '<entml:invoke name="Read">\n'
        '<entml:parameter name="path">X:/Project/Local/DeepSeek/core/guard/pow.py</entml:parameter>\n'
        '<entml:parameter name="line_offset">143</entml:parameter>\n'
        '<entml:parameter name="n_lines">15</entml:parameter>\n'
        "</entml:invoke>"
    )
    proto = get_protocol("entml")
    batch_args = json.loads(proto.parse(text, tools)[1][0]["function"]["arguments"])
    parser = FncallStreamParser(protocol=proto, tools=tools)
    json_buf = ""
    for i in range(0, len(text), 17):
        parser.feed(text[i : i + 17])
        while True:
            delta = parser.consume_stream_delta()
            if not delta:
                break
            json_buf += delta[1]
    comp = parser.complete_stream_delta_if_needed()
    if comp:
        json_buf += comp[1]
    parser.finalize()
    assert json.loads(json_buf) == batch_args
    assert batch_args == {
        "path": "X:/Project/Local/DeepSeek/core/guard/pow.py",
        "line_offset": 143,
        "n_lines": 15,
    }


BASH_TOOLS = [
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


def test_mangled_json_tail_in_command_param_batch_and_stream() -> None:
    """未闭合 parameter + JSON 尾缀误写入 command：batch/stream json_buf 须可解析且一致。"""
    from pathlib import Path

    text = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785296513-7782eb161d4d.txt"
    ).read_text(encoding="utf-8")
    proto = get_protocol("entml")
    batch_args = json.loads(proto.parse(text, BASH_TOOLS)[1][0]["function"]["arguments"])
    assert "command" in batch_args
    assert batch_args["command"].endswith("head -60\"")
    assert "description" not in batch_args["command"]
    assert batch_args.get("description")
    assert batch_args.get("timeout") == 30000

    for chunk in (1, 17, 64):
        parser = FncallStreamParser(protocol=proto, tools=BASH_TOOLS)
        json_buf = ""
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
            while True:
                delta = parser.consume_stream_delta()
                if not delta:
                    break
                json_buf += delta[1]
        comp = parser.complete_stream_delta_if_needed()
        if comp:
            json_buf += comp[1]
        parser.finalize()
        assert json.loads(json_buf) == batch_args, f"chunk={chunk}"


ASK_USER_QUESTION_TOOLS = [
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


def test_ask_user_question_array_param_not_split_on_description_key() -> None:
    """JSON 数组参数内的 ``description`` 字段不得触发 mangled command 尾缀截断。"""
    from pathlib import Path

    text = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785299204-c84e955dbf7d.txt"
    ).read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(text, ASK_USER_QUESTION_TOOLS)
    batch_args = json.loads(batch_calls[0]["function"]["arguments"])
    assert isinstance(batch_args["questions"], list)
    assert batch_args["questions"][0]["options"][0]["description"]

    for chunk in (1, 17, 64):
        parser = FncallStreamParser(protocol=proto, tools=ASK_USER_QUESTION_TOOLS)
        json_buf = ""
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
            while True:
                delta = parser.consume_stream_delta()
                if not delta:
                    break
                json_buf += delta[1]
        comp = parser.complete_stream_delta_if_needed()
        if comp:
            json_buf += comp[1]
        parser.finalize()
        assert json.loads(json_buf) == batch_args, f"chunk={chunk}"


def test_parameters_block_no_stream_until_closed() -> None:
    body = (
        "<entml:parameters>\n"
        '{"query":"x","limit":1'
    )
    snap = build_streaming_json_snapshot(
        body,
        tool_name="search_web",
        schema_index=_build_param_schema_index(TOOLS),
    )
    assert snap == ""
    closed = body + '}\n</entml:parameters>'
    snap2 = build_streaming_json_snapshot(
        closed,
        tool_name="search_web",
        schema_index=_build_param_schema_index(TOOLS),
    )
    assert json.loads(snap2) == {"query": "x", "limit": 1}


@pytest.mark.parametrize("chunk", [1, 5, 17])
def test_agent_write_stream_parity(chunk: int) -> None:
    """Windows Write 路径：merged partial_json 必须等于 batch。"""
    case = _WRITE_CASE
    tools = tools_for_case(case)
    proto = get_protocol("entml")
    _, batch_calls = proto.parse(case.response, tools)
    parser = FncallStreamParser(protocol=proto, tools=tools)
    merged = ""
    for i in range(0, len(case.response), chunk):
        parser.feed(case.response[i : i + chunk])
        d = parser.consume_stream_delta()
        if d:
            merged += d[1]
    parser.finalize()
    batch_args = json.loads(batch_calls[0]["function"]["arguments"])
    assert json.loads(merged) == batch_args
