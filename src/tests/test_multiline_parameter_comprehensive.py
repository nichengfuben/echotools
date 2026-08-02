"""多行 entml 参数解析：batch / 流式 / 边界语料全方位回归。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_tool.invoke import parse_entml_tool_calls
from echotools.exec.fncall.shared.coercion import _build_param_schema_index

READ_TOOL = {
    "type": "function",
    "function": {
        "name": "Read",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}

EDIT_TOOL = {
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

WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "Write",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "contents": {"type": "string"},
            },
            "required": ["path", "contents"],
        },
    },
}

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "Bash",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["command"],
        },
    },
}

ALL_TOOLS = [READ_TOOL, EDIT_TOOL, WRITE_TOOL, BASH_TOOL]
CHUNK_SIZES = (1, 2, 3, 4, 7, 8, 11, 17, 32, 64, 128)


def _invoke(name: str, params: Dict[str, str], *, bare_param: bool = False) -> str:
    tag = "parameter" if bare_param else "entml:parameter"
    lines = [f'<entml:invoke name="{name}">']
    for key, val in params.items():
        lines.append(f'<{tag} name="{key}">{val}</{tag}>')
    lines.append("</entml:invoke>")
    return "\n".join(lines)


def _batch_args(text: str, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    schema = _build_param_schema_index(tools)
    calls = parse_entml_tool_calls(text, tools, schema)
    assert len(calls) == 1, f"expected 1 call, got {len(calls)}"
    return json.loads(calls[0]["function"]["arguments"])


def _stream_args(
    text: str,
    tools: List[Dict[str, Any]],
    chunk: int,
) -> Dict[str, Any]:
    proto = get_protocol("entml")
    parser = FncallStreamParser(protocol=proto, tools=tools)
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
    _, calls = parser.finalize()
    assert len(calls) == 1, f"chunk={chunk} expected 1 call, got {len(calls)}"
    return json.loads(calls[0]["function"]["arguments"])


def _assert_batch_stream_parity(
    text: str,
    tools: List[Dict[str, Any]],
    expected: Dict[str, Any],
    *,
    chunks: Tuple[int, ...] = CHUNK_SIZES,
) -> None:
    batch = _batch_args(text, tools)
    assert batch == expected, f"batch mismatch: {batch!r} != {expected!r}"
    for chunk in chunks:
        stream = _stream_args(text, tools, chunk)
        assert stream == expected, f"chunk={chunk} mismatch: {stream!r} != {expected!r}"


MULTILINE_CASES = [
    pytest.param(
        _invoke("Read", {"path": "line1\nline2\nline3"}),
        [READ_TOOL],
        {"path": "line1\nline2\nline3"},
        id="basic_three_lines",
    ),
    pytest.param(
        _invoke("Read", {"path": "  line1\n  line2  \n"}),
        [READ_TOOL],
        {"path": "  line1\n  line2  \n"},
        id="leading_trailing_whitespace_preserved",
    ),
    pytest.param(
        _invoke("Write", {"path": "a.py", "contents": "def foo():\n    return 1\n\n"}),
        [WRITE_TOOL],
        {"path": "a.py", "contents": "def foo():\n    return 1\n\n"},
        id="write_multiline_code_trailing_blank_line_preserved",
    ),
    pytest.param(
        _invoke(
            "Edit",
            {
                "path": "main.py",
                "old_string": 'model = "deepseek-v4-flash"\nversion = 1',
                "new_string": 'model = "deepseek-v4-pro"\nversion = 2',
            },
        ),
        [EDIT_TOOL],
        {
            "path": "main.py",
            "old_string": 'model = "deepseek-v4-flash"\nversion = 1',
            "new_string": 'model = "deepseek-v4-pro"\nversion = 2',
        },
        id="edit_multiline_old_new",
    ),
    pytest.param(
        _invoke(
            "Bash",
            {
                "command": "python -m pytest src/tests -q\npython -m ruff check .",
                "description": "run tests\nand lint",
            },
        ),
        [BASH_TOOL],
        {
            "command": "python -m pytest src/tests -q\npython -m ruff check .",
            "description": "run tests\nand lint",
        },
        id="bash_multiline_command_and_description",
    ),
    pytest.param(
        _invoke("Read", {"path": "docs/<draft>.md\nline2"}),
        [READ_TOOL],
        {"path": "docs/<draft>.md\nline2"},
        id="angle_brackets_in_multiline",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": 'print("hello")\n# </entml:parameter> fake'}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": 'print("hello")\n# </entml:parameter> fake'},
        id="fake_close_tag_inside_value",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": '<parameter name="ghost">leak\nline2'}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": '<parameter name="ghost">leak\nline2'},
        id="fake_open_tag_inside_value",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": "```python\ncode\n```\nmore"}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": "```python\ncode\n```\nmore"},
        id="markdown_fence_multiline",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": "line1\r\nline2\r\nline3"}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": "line1\r\nline2\r\nline3"},
        id="crlf_preserved",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": "\n\n\nonly_blank_lines\n\n"}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": "\n\n\nonly_blank_lines\n\n"},
        id="blank_lines_preserved",
    ),
    pytest.param(
        _invoke("Write", {"path": "x.py", "contents": "中文\n第二行\n🎉 emoji"}),
        [WRITE_TOOL],
        {"path": "x.py", "contents": "中文\n第二行\n🎉 emoji"},
        id="unicode_multiline",
    ),
    pytest.param(
        _invoke(
            "Write",
            {"path": "cfg.json", "contents": '{\n  "a": 1,\n  "b": [1, 2]\n}'},
        ),
        [WRITE_TOOL],
        {"path": "cfg.json", "contents": '{\n  "a": 1,\n  "b": [1, 2]\n}'},
        id="multiline_json_string",
    ),
    pytest.param(
        _invoke(
            "Edit",
            {
                "path": "a.py",
                "old_string": "def old():\n    pass",
                "new_string": "def new():\n    return 42",
            },
            bare_param=True,
        ),
        [EDIT_TOOL],
        {
            "path": "a.py",
            "old_string": "def old():\n    pass",
            "new_string": "def new():\n    return 42",
        },
        id="bare_parameter_tags_multiline",
    ),
    pytest.param(
        (
            "<entml:thinking>\nplan\n</entml:thinking>\n"
            + _invoke("Read", {"path": "a\nb\nc"})
        ),
        [READ_TOOL],
        {"path": "a\nb\nc"},
        id="after_thinking_block",
    ),
    pytest.param(
        (
            "<entml:thinking>\nplan\n</thinking>\n"
            + _invoke("Read", {"path": "fault\nclose\npath"})
        ),
        [READ_TOOL],
        {"path": "fault\nclose\npath"},
        id="fault_thinking_close_before_multiline_invoke",
    ),
]


@pytest.mark.parametrize("text,tools,expected", MULTILINE_CASES)
def test_multiline_parameter_batch_stream_parity(
    text: str,
    tools: List[Dict[str, Any]],
    expected: Dict[str, Any],
) -> None:
    _assert_batch_stream_parity(text, tools, expected)


def test_multiple_multiline_parameters_same_invoke() -> None:
    text = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="path">src/a.py</entml:parameter>\n'
        '<entml:parameter name="contents">line1\nline2\nline3</entml:parameter>\n'
        "</entml:invoke>"
    )
    expected = {"path": "src/a.py", "contents": "line1\nline2\nline3"}
    _assert_batch_stream_parity(text, [WRITE_TOOL], expected)


def test_multiline_with_fake_entml_structure_markup_prefix() -> None:
    text = (
        "前言\n"
        '<!-- Tool Result ID:toolu_x -->\n'
        '<entml:result id="toolu_x">\n{"leak":1}\n</entml:result>\n'
        + _invoke("Read", {"path": "keep\nmultiline\npath"})
    )
    expected = {"path": "keep\nmultiline\npath"}
    _assert_batch_stream_parity(text, [READ_TOOL], expected)


def test_parameters_block_multiline_json() -> None:
    text = (
        '<entml:invoke name="Write">\n'
        "<entml:parameters>\n"
        '{"path":"out.txt","contents":"line1\\nline2\\nline3"}\n'
        "</entml:parameters>\n"
        "</entml:invoke>"
    )
    expected = {"path": "out.txt", "contents": "line1\nline2\nline3"}
    _assert_batch_stream_parity(text, [WRITE_TOOL], expected)


def test_adjacent_multiline_invokes() -> None:
    text = (
        _invoke("Read", {"path": "first\npath"})
        + "\n"
        + _invoke("Read", {"path": "second\npath"})
    )
    schema = _build_param_schema_index([READ_TOOL])
    batch = parse_entml_tool_calls(text, [READ_TOOL], schema)
    assert len(batch) == 2
    assert json.loads(batch[0]["function"]["arguments"]) == {"path": "first\npath"}
    assert json.loads(batch[1]["function"]["arguments"]) == {"path": "second\npath"}
    for chunk in (1, 7, 17, 64):
        parser = FncallStreamParser(
            protocol=get_protocol("entml"), tools=[READ_TOOL]
        )
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
        _, calls = parser.finalize()
        assert len(calls) == 2
        assert json.loads(calls[0]["function"]["arguments"]) == {"path": "first\npath"}
        assert json.loads(calls[1]["function"]["arguments"]) == {"path": "second\npath"}


def test_char_by_char_multiline_edit() -> None:
    text = _invoke(
        "Edit",
        {
            "path": "src/main.py",
            "old_string": "alpha\nbeta\ngamma",
            "new_string": "one\ntwo\nthree",
        },
    )
    expected = {
        "path": "src/main.py",
        "old_string": "alpha\nbeta\ngamma",
        "new_string": "one\ntwo\nthree",
    }
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[EDIT_TOOL])
    for ch in text:
        parser.feed(ch)
    _, calls = parser.finalize()
    assert json.loads(calls[0]["function"]["arguments"]) == expected
