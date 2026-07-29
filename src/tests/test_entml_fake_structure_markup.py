from __future__ import annotations

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_fake_structure_markup import (
    strip_fake_entml_structure_markup,
    strip_fake_entml_structure_markup_for_display,
)
from echotools.exec.fncall.protocols.entml_tool_result_comment import (
    strip_complete_tool_result_id_comments,
    trailing_partial_tool_result_id_comment_len,
)

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


@pytest.mark.parametrize(
    "raw,expect_sub,expect_absent",
    [
        (
            '前言\n<!-- Tool Result ID:toolu_f1a2b3c4 -->\n后缀',
            "前言",
            "Tool Result ID",
        ),
        (
            '可见\n<entml:result id="toolu_46bd973b2dbd48e681b54714">\n{"ok":1}\n</entml:result>\n尾',
            "可见",
            "entml:result",
        ),
        (
            "说明\n<entml:funtions_results>\n</entml:funtions_results>\n继续",
            "说明",
            "funtions_results",
        ),
        (
            "正文\n<entml:conversation_history>\n</entml:conversation_history>\n完",
            "正文",
            "conversation_history",
        ),
        (
            "<entml:result>\nbody\n</entml:result>\nok",
            "ok",
            "entml:result",
        ),
    ],
)
def test_strip_fake_entml_structure_batch(
    raw: str,
    expect_sub: str,
    expect_absent: str,
) -> None:
    cleaned, found = strip_fake_entml_structure_markup(raw)
    assert found
    assert expect_sub in cleaned
    assert expect_absent not in cleaned


def test_tool_result_comment_partial_hold() -> None:
    partial = "可见\n<!-- Tool Result ID:toolu_abc"
    assert trailing_partial_tool_result_id_comment_len(partial) == len(
        "<!-- Tool Result ID:toolu_abc"
    )
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "可见\n"
    assert "Tool Result ID" not in display


def test_open_tag_stripped_at_gt_without_close_tag() -> None:
    partial = "前言\n<entml:funtions_results>"
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "前言\n"
    partial2 = "x\n<entml:conversation_history"
    display2, _ = strip_fake_entml_structure_markup_for_display(partial2)
    assert display2 == "x\n"


def test_result_open_holds_until_gt() -> None:
    partial = '可见\n<entml:result id="toolu_x'
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "可见\n"
    complete = partial + '">\nleak'
    display2, _ = strip_fake_entml_structure_markup_for_display(complete)
    assert "entml:result" not in display2
    assert "leak" not in display2


def test_batch_parse_strips_fake_structure() -> None:
    text = (
        "回答正文\n"
        '<!-- Tool Result ID:call_0000 -->\n'
        '<entml:result id="toolu_abc">\n{"x":1}\n</entml:result>\n'
        "<entml:funtions_results>\n</entml:funtions_results>"
    )
    proto = get_protocol("entml")
    clean, calls = proto.parse(text, [READ_TOOL])
    assert calls == []
    assert "回答正文" in clean
    assert "Tool Result ID" not in clean
    assert "entml:result" not in clean
    assert "funtions_results" not in clean


@pytest.mark.parametrize("chunk", [1, 4, 17, 32])
def test_stream_partial_no_fake_structure_leak(chunk: int) -> None:
    text = (
        "流式可见\n"
        '<!-- Tool Result ID:toolu_leak -->\n'
        '<entml:result id="toolu_x">\n{"fake":true}\n</entml:result>\n'
        "<entml:conversation_history>\n"
    )
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
    for i in range(0, len(text), chunk):
        parser.feed(text[i : i + chunk])
        pt = parser.partial_text
        assert "Tool Result ID" not in pt
        assert "entml:result" not in pt
        assert "conversation_history" not in pt
        assert "fake" not in pt
    clean, calls = parser.finalize()
    assert calls == []
    assert "流式可见" in clean
    assert "Tool Result ID" not in clean
