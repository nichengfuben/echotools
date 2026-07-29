from __future__ import annotations

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_fake_structure_markup import (
    strip_fake_entml_structure_markup,
    strip_fake_entml_structure_markup_for_display,
)
from echotools.exec.fncall.protocols.entml_tool_result_comment import (
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
    "raw,expect_sub,expect_absent,expect_present",
    [
        (
            '前言\n<!-- Tool Result ID:toolu_f1a2b3c4 -->\n后缀',
            "前言",
            "Tool Result ID",
            None,
        ),
        (
            '可见\n<entml:result id="toolu_46bd973b2dbd48e681b54714">\n{"ok":1}\n</entml:result>\n尾',
            "可见",
            '{"ok":1}',
            "尾",
        ),
        (
            "说明\n<entml:funtions_results>\n假正文\n</entml:funtions_results>\n继续",
            "假正文",
            "funtions_results",
            "继续",
        ),
        (
            "正文\n<entml:conversation_history>\n历史假数据\n</entml:conversation_history>\n完",
            "历史假数据",
            "conversation_history",
            "完",
        ),
        (
            "前\n<entml:calls>\n调用块正文\n</entml:calls>\n后",
            "调用块正文",
            "entml:calls",
            "后",
        ),
        (
            "前\n<function_calling_behavior>\n行为块正文\n</function_calling_behavior>\n后",
            "行为块正文",
            "function_calling_behavior",
            "后",
        ),
        (
            "前\n<thinking_behavior>\n思考行为\n</thinking_behavior>\n后",
            "思考行为",
            "thinking_behavior",
            "后",
        ),
        (
            "<entml:result>\nbody\n</entml:result>\nok",
            "body",
            "entml:result",
            "ok",
        ),
    ],
)
def test_strip_fake_entml_structure_batch(
    raw: str,
    expect_sub: str,
    expect_absent: str,
    expect_present: str | None,
) -> None:
    cleaned, found = strip_fake_entml_structure_markup(raw)
    assert found
    assert expect_sub in cleaned
    assert expect_absent not in cleaned
    if expect_present:
        assert expect_present in cleaned


def test_tool_result_comment_partial_hold() -> None:
    partial = "可见\n<!-- Tool Result ID:toolu_abc"
    assert trailing_partial_tool_result_id_comment_len(partial) == len(
        "<!-- Tool Result ID:toolu_abc"
    )
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "可见\n"
    assert "Tool Result ID" not in display


def test_open_tag_stripped_at_gt_content_kept() -> None:
    partial = "前言\n<entml:funtions_results>"
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "前言\n"
    raw = "前言\n<entml:funtions_results>保留正文"
    cleaned, _ = strip_fake_entml_structure_markup(raw)
    assert cleaned == "前言\n保留正文"
    assert "funtions_results" not in cleaned


def test_result_id_block_holds_and_strips_body() -> None:
    partial = '可见\n<entml:result id="toolu_x'
    display, found = strip_fake_entml_structure_markup_for_display(partial)
    assert found
    assert display == "可见\n"
    complete = partial + '">\nleak'
    display2, _ = strip_fake_entml_structure_markup_for_display(complete)
    assert "entml:result" not in display2
    assert "leak" not in display2


def test_bare_result_tags_only_not_body() -> None:
    raw = "可见\n<entml:result>\n正文保留\n</entml:result>\n尾"
    cleaned, found = strip_fake_entml_structure_markup(raw)
    assert found
    assert "正文保留" in cleaned
    assert "entml:result" not in cleaned
    assert "可见" in cleaned
    assert "尾" in cleaned


def test_orphan_incomplete_entml_close_leak() -> None:
    raw = (
        "说明正文\n"
        "<!-- Tool Result ID:toolu_check_theme_btn -->\n"
        "</entml:"
    )
    cleaned, found = strip_fake_entml_structure_markup(raw)
    assert found
    assert "说明正文" in cleaned
    assert "entml" not in cleaned.lower()
    assert "Tool Result ID" not in cleaned


def test_rogator_response_log_corpus_no_entml_tail() -> None:
    from pathlib import Path

    log = Path(__file__).resolve().parent / "fixtures" / "rogator_entml_close_leak.txt"
    raw = log.read_text(encoding="utf-8")
    READ = {
        "type": "function",
        "function": {
            "name": "Grep",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    }
    proto = get_protocol("entml")
    clean, calls = proto.parse(raw, [READ])
    assert calls
    assert "entml" not in clean.lower()


def test_batch_parse_strips_fake_structure() -> None:
    text = (
        "回答正文\n"
        '<!-- Tool Result ID:call_0000 -->\n'
        '<entml:result id="toolu_abc">\n{"x":1}\n</entml:result>\n'
        "<entml:funtions_results>\n标签间保留\n</entml:funtions_results>"
    )
    proto = get_protocol("entml")
    clean, calls = proto.parse(text, [READ_TOOL])
    assert calls == []
    assert "回答正文" in clean
    assert "Tool Result ID" not in clean
    assert "entml:result" not in clean
    assert '{"x":1}' not in clean
    assert "标签间保留" in clean
    assert "funtions_results" not in clean


@pytest.mark.parametrize("chunk", [1, 4, 17, 32])
def test_stream_partial_no_fake_structure_leak(chunk: int) -> None:
    text = (
        "流式可见\n"
        '<!-- Tool Result ID:toolu_leak -->\n'
        '<entml:result id="toolu_x">\n{"fake":true}\n</entml:result>\n'
        "<entml:conversation_history>\n中间保留\n"
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
    assert "中间保留" in clean
    assert "Tool Result ID" not in clean
