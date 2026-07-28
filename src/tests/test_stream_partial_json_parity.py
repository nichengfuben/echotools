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
