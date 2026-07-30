from __future__ import annotations

"""流式 partial_json 专项边界（语料矩阵见 test_model_branch_matrix.py）。"""

import json

import pytest
from fixtures.simulated_llm_tool_responses import (
    TOOLS,
    iter_cases_with_tools,
    tools_for_case,
)

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_stream import (
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


EDIT_TOOLS = [
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


def test_edit_params_with_embedded_description_json_not_truncated() -> None:
    """内嵌 ``", \"description\"`` 的自由文本不得被 mangled-tail 截断（不靠参数名特判）。"""
    old = (
        '    parameters={\n'
        '            "type": "object",\n'
        '            "properties": {\n'
        '                "query": {"type": "string", "description": "The HTTP or HTTPS URL to fetch."},\n'
        '                "method": {"type": "string", "description": "HTTP method"},\n'
        '            },\n'
        '            "required": ["url"],\n'
        '        },\n'
        '        requires_approval=True,\n'
        '    )'
    )
    new = (
        '    parameters={\n'
        '            "type": "object",\n'
        '            "properties": {\n'
        '                "query": {"type": "string", "description": "The search query string."},\n'
        '                "count": {"type": "integer", "description": "Number of results"},\n'
        '            },\n'
        '            "required": ["query"],\n'
        '        },\n'
        '        requires_approval=False,\n'
        '    )'
    )
    assert old != new
    # 故意用非 Edit 专用参数名，确保修复是后缀结构判定而非名字黑名单
    tools = [
        {
            "type": "function",
            "function": {
                "name": "ApplyChange",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "before": {"type": "string"},
                        "after": {"type": "string"},
                    },
                    "required": ["target", "before", "after"],
                },
            },
        }
    ]
    text = (
        '<entml:thinking>fix</entml:thinking>\n'
        '<entml:invoke name="ApplyChange">\n'
        '<entml:parameter name="target">src/server/tools/registry.py</entml:parameter>\n'
        f'<entml:parameter name="before">{old}</entml:parameter>\n'
        f'<entml:parameter name="after">{new}</entml:parameter>\n'
        '</entml:invoke>\n'
    )
    proto = get_protocol("entml")
    _, calls = proto.parse(text, tools)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["before"] == old.strip()
    assert args["after"] == new.strip()
    assert args["before"] != args["after"]
    assert '"method"' in args["before"]
    assert '"count"' in args["after"]

    for chunk in (1, 17, 64, 256):
        parser = FncallStreamParser(protocol=proto, tools=tools)
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
        _, stream_calls = parser.finalize()
        stream_args = json.loads(stream_calls[0]["function"]["arguments"])
        assert stream_args == args, f"chunk={chunk}"


def test_edit_corpus_req_1785406974_not_truncated() -> None:
    """真实语料：模型 Edit 完整，解析器不得把 old/new 截到相同的 ``\"string\"`` 前缀。"""
    from pathlib import Path

    path = Path(r"X:/Project/Public/Qwen/logs/responses/req-1785406974-586c810869b9.txt")
    if not path.is_file():
        import pytest

        pytest.skip("corpus missing")
    text = path.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    _, calls = proto.parse(text, EDIT_TOOLS)
    args = json.loads(calls[0]["function"]["arguments"])
    assert "description\": \"The search query string." in args["new_string"]
    assert "execute_web_search" in args["new_string"]
    assert "execute_web_fetch" in args["old_string"]
    assert args["old_string"] != args["new_string"]
    assert not args["old_string"].endswith('"string"')


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


@pytest.mark.parametrize("chunk", [1, 16, 64, 512])
def test_large_bash_bare_description_stream_parity(chunk: int) -> None:
    """大 Bash command + bare description/timeout：流式 json_buf 须单调且与 batch 一致（6537）。"""
    from pathlib import Path

    text_path = Path(
        r"X:/Project/Public/Qwen/logs/responses/req-1785309429-9436e01561b2.txt"
    )
    if not text_path.is_file():
        pytest.skip("fixture log not available")
    text = text_path.read_text(encoding="utf-8")
    start = text.index('<entml:invoke name="Bash">')
    end = text.index("</entml:invoke>", start) + len("</entml:invoke>")
    sample = text[start:end]

    proto = get_protocol("entml")
    batch_args = json.loads(proto.parse(sample, BASH_TOOLS)[1][0]["function"]["arguments"])

    parser = FncallStreamParser(protocol=proto, tools=BASH_TOOLS)
    json_buf = ""
    prev_len = 0
    for i in range(0, len(sample), chunk):
        parser.feed(sample[i : i + chunk])
        while True:
            delta = parser.consume_stream_delta()
            if not delta:
                break
            json_buf += delta[1]
        assert len(json_buf) >= prev_len, f"non-monotonic at offset {i}"
        prev_len = len(json_buf)
    comp = parser.complete_stream_delta_if_needed()
    if comp:
        json_buf += comp[1]
    parser.finalize()
    assert json.loads(json_buf) == batch_args


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
