from __future__ import annotations

"""invoke 仅在闭合 ``>`` 且 name 属于已知 tools 时才解析/过滤。"""

import json
from typing import Any, Dict, List, Optional

import pytest

from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml import EntmlProtocol
from echotools.exec.fncall.protocols.entml_patterns import (
    entml_invoke_open_is_actionable,
    entml_invoke_open_may_be_streaming,
    find_actionable_entml_invoke_open,
    iter_actionable_entml_invoke_blocks,
    resolve_known_tool_names,
    strip_actionable_entml_invoke_blocks,
)
from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall import get_protocol


READ_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "Read",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        },
    }
]

USER_CASE = (
    "我明白了，让我用 `<entml:invoke>` 格式串行测试每个可用的工具。\n\n"
    "**第一步：测试 Read 工具** — 读取一个已存在的文件\n\n"
    '<entml:invoke name="Read">\n'
    '<entml:parameter name="file_path">C:\\Users\\Administrator\\.claude\\CLAUDE.md</entml:parameter>\n'
    "</entml:invoke>"
)


def _known(tools: Optional[List[Dict[str, Any]]] = None):
    schema = _build_param_schema_index(tools) if tools else None
    return resolve_known_tool_names(tools, schema)


class TestInvokeActionableGate:
    def test_prose_invoke_without_name_not_actionable(self) -> None:
        text = "使用 `<entml:invoke>` 格式"
        pos = text.index("<entml:invoke")
        known = _known(READ_TOOLS)
        assert not entml_invoke_open_is_actionable(text, pos, known_names=known)
        assert not entml_invoke_open_may_be_streaming(text, pos, known_names=known)

    def test_partial_invoke_may_stream_but_not_actionable(self) -> None:
        text = '前文<entml:invoke name="Re'
        pos = text.index("<entml:invoke")
        known = _known(READ_TOOLS)
        assert not entml_invoke_open_is_actionable(text, pos, known_names=known)
        assert entml_invoke_open_may_be_streaming(text, pos, known_names=known)

    def test_closed_unknown_tool_not_actionable(self) -> None:
        text = '<entml:invoke name="UnknownTool">\n</entml:invoke>'
        pos = text.index("<entml:invoke")
        known = _known(READ_TOOLS)
        assert not entml_invoke_open_is_actionable(text, pos, known_names=known)
        assert not entml_invoke_open_may_be_streaming(text, pos, known_names=known)

    def test_closed_known_tool_is_actionable(self) -> None:
        text = '<entml:invoke name="Read">\n</entml:invoke>'
        pos = text.index("<entml:invoke")
        known = _known(READ_TOOLS)
        assert entml_invoke_open_is_actionable(text, pos, known_names=known)

    def test_placeholder_name_not_actionable(self) -> None:
        text = '<entml:invoke name="$FUNCTION_NAME">\n</entml:invoke>'
        pos = text.index("<entml:invoke")
        assert not entml_invoke_open_is_actionable(text, pos, known_names=_known(READ_TOOLS))

    def test_find_actionable_skips_prose_then_finds_real(self) -> None:
        known = _known(READ_TOOLS)
        pos = find_actionable_entml_invoke_open(USER_CASE, known_names=known)
        assert pos == USER_CASE.index('<entml:invoke name="Read">')
        blocks = list(iter_actionable_entml_invoke_blocks(USER_CASE, known_names=known))
        assert len(blocks) == 1


class TestBatchParseKnownToolGate:
    def test_user_case_parses_read_only(self) -> None:
        proto = EntmlProtocol()
        clean, calls = proto.parse(USER_CASE, READ_TOOLS)
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "Read"
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["file_path"].endswith("CLAUDE.md")
        assert "`<entml:invoke>`" in clean or "<entml:invoke>" in clean
        assert '<entml:invoke name="Read">' not in clean

    def test_unknown_invoke_not_parsed_or_stripped(self) -> None:
        proto = EntmlProtocol()
        text = (
            "说明 `<entml:invoke>` 用法\n"
            '<entml:invoke name="Ghost">\n'
            '<entml:parameter name="x">1</entml:parameter>\n'
            "</entml:invoke>"
        )
        clean, calls = proto.parse(text, READ_TOOLS)
        assert calls == []
        assert '<entml:invoke name="Ghost">' in clean

    def test_mixed_known_and_unknown_only_strips_known(self) -> None:
        proto = EntmlProtocol()
        text = (
            '<entml:invoke name="Ghost">\n</entml:invoke>\n'
            '<entml:invoke name="Read">\n'
            '<entml:parameter name="file_path">a.txt</entml:parameter>\n'
            "</entml:invoke>"
        )
        clean, calls = proto.parse(text, READ_TOOLS)
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "Read"
        assert "Ghost" in clean
        assert '<entml:invoke name="Read">' not in clean

    def test_strip_respects_known_names(self) -> None:
        known = _known(READ_TOOLS)
        text = (
            "`<entml:invoke>`\n"
            '<entml:invoke name="Read">x</entml:invoke>\n'
            '<entml:invoke name="Ghost">y</entml:invoke>'
        )
        out = strip_actionable_entml_invoke_blocks(text, known_names=known)
        assert "`<entml:invoke>`" in out
        assert "Ghost" in out
        assert '<entml:invoke name="Read">' not in out


@pytest.mark.parametrize("chunk_size", [1, 7, 17, 64, 256])
class TestStreamKnownToolGate:
    def test_user_case_stream_matches_batch(self, chunk_size: int) -> None:
        proto = get_protocol("entml")
        batch_clean, batch_calls = proto.parse(USER_CASE, READ_TOOLS)
        parser = FncallStreamParser(protocol=proto, tools=READ_TOOLS)
        for i in range(0, len(USER_CASE), chunk_size):
            parser.feed(USER_CASE[i : i + chunk_size])
        stream_clean, stream_calls = parser.finalize()
        assert len(stream_calls) == len(batch_calls) == 1
        assert stream_calls[0]["function"]["name"] == "Read"
        assert json.loads(stream_calls[0]["function"]["arguments"]) == json.loads(
            batch_calls[0]["function"]["arguments"]
        )
        assert "`<entml:invoke>`" in stream_clean or "<entml:invoke>" in stream_clean

    def test_prose_invoke_visible_before_real_invoke(self, chunk_size: int) -> None:
        proto = get_protocol("entml")
        parser = FncallStreamParser(protocol=proto, tools=READ_TOOLS)
        prefix = USER_CASE[: USER_CASE.index('<entml:invoke name="Read">')]
        for i in range(0, len(prefix), chunk_size):
            parser.feed(USER_CASE[i : i + chunk_size])
        partial = parser.partial_text
        assert "`<entml:invoke>`" in partial or "<entml:invoke>" in partial

    def test_unknown_invoke_never_enters_tool_mode(self, chunk_size: int) -> None:
        proto = get_protocol("entml")
        text = (
            "`<entml:invoke>`\n"
            '<entml:invoke name="Ghost">\n'
            '<entml:parameter name="x">1</entml:parameter>\n'
            "</entml:invoke>"
        )
        parser = FncallStreamParser(protocol=proto, tools=READ_TOOLS)
        for i in range(0, len(text), chunk_size):
            parser.feed(text[i : i + chunk_size])
        clean, calls = parser.finalize()
        assert calls == []
        assert "Ghost" in clean


class TestDetectStartGate:
    def test_detect_start_false_on_prose_only(self) -> None:
        proto = EntmlProtocol()
        found, pos = proto.detect_start("使用 `<entml:invoke>`", tools=READ_TOOLS)
        assert found is False
        assert pos == -1

    def test_detect_start_false_on_unknown_closed(self) -> None:
        proto = EntmlProtocol()
        found, pos = proto.detect_start(
            '<entml:invoke name="Ghost">', tools=READ_TOOLS
        )
        assert found is False

    def test_detect_start_true_on_known_closed(self) -> None:
        proto = EntmlProtocol()
        text = '<entml:invoke name="Read">'
        found, pos = proto.detect_start(text, tools=READ_TOOLS)
        assert found is True
        assert pos == 0

    def test_hold_on_partial_not_on_prose(self) -> None:
        proto = EntmlProtocol()
        assert proto.find_fncall_hold_from("`<entml:invoke>`", tools=READ_TOOLS) is None
        partial = '<entml:invoke name="Re'
        hold = proto.find_fncall_hold_from(partial, tools=READ_TOOLS)
        assert hold == partial.index("<entml:invoke")


class TestNoToolsBackwardCompat:
    def test_without_tools_any_named_invoke_actionable(self) -> None:
        text = '<entml:invoke name="Anything">\n</entml:invoke>'
        pos = 0
        assert entml_invoke_open_is_actionable(text, pos, known_names=None)
        proto = EntmlProtocol()
        found, _ = proto.detect_start(text, tools=None)
        assert found is True
