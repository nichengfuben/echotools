from __future__ import annotations

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.protocols.entml_tool.comment import (
    trailing_partial_tool_result_id_comment_len,
)
from echotools.exec.fncall.protocols.entml_tool.fakemarkup import (
    strip_fake_entml_structure_markup,
    strip_fake_entml_structure_markup_for_display,
    strip_orphan_entml_close_tags,
)

_REDACTED_THINKING = "redacted" + "_thinking"

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
            "前\n<entml:call>\n调用块正文\n</entml:call>\n后",
            "调用块正文",
            "entml:call",
            "后",
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
            "前\n<entml:hard_constraint_restatement>\n硬约束复述\n</entml:hard_constraint_restatement>\n后",
            "硬约束复述",
            "hard_constraint_restatement",
            "后",
        ),
        (
            "正文\n<function_results>\n假结果\n</function_results>\n继续",
            "假结果",
            "function_results",
            "继续",
        ),
        (
            "除此之外</function_result>，中间保留",
            "中间保留",
            "function_result",
            "除此之外",
        ),
        (
            "<entml:result>\nbody\n</entml:result>\nok",
            "body",
            "entml:result",
            "ok",
        ),
        (
            "除此之外</entml:todo>，<entml:todo>只过滤标签",
            "只过滤标签",
            "entml:todo",
            "除此之外",
        ),
        (
            "前\n<entml:todo>\n正文保留\n</entml:todo>\n后",
            "正文保留",
            "entml:todo",
            "后",
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


def test_strip_redacted_thinking_tags_only() -> None:
    rt = _REDACTED_THINKING
    raw = f"前\n<{rt}>\n已脱敏思考\n</{rt}>\n后"
    cleaned, found = strip_fake_entml_structure_markup(raw)
    assert found
    assert rt not in cleaned
    assert "已脱敏思考" in cleaned
    assert "后" in cleaned


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


def test_orphan_complete_entml_close_after_invoke_strip() -> None:
    cleaned, found = strip_orphan_entml_close_tags("完成编辑\n</entml:invoke>")
    assert found
    assert cleaned.strip() == "完成编辑"
    rest, found2 = strip_orphan_entml_close_tags("前\n后\n</entml:invoke>")
    assert found2
    assert "前" in rest and "后" in rest
    assert "entml" not in rest.lower()


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
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
}


def test_rogator_edit_triple_invoke_corpus_batch() -> None:
    from pathlib import Path

    log = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "rogator_edit_triple_orphan_close.txt"
    )
    raw = log.read_text(encoding="utf-8")
    proto = get_protocol("entml")
    clean, calls = proto.parse(raw, [EDIT_TOOL])
    assert len(calls) == 3
    assert all(c["function"]["name"] == "Edit" for c in calls)
    assert "entml" not in clean.lower()
    assert "main.py" in clean


@pytest.mark.parametrize("chunk", [1, 4, 8, 17, 32])
def test_rogator_edit_triple_invoke_corpus_stream(chunk: int) -> None:
    from pathlib import Path

    log = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "rogator_edit_triple_orphan_close.txt"
    )
    raw = log.read_text(encoding="utf-8")
    parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[EDIT_TOOL])
    for i in range(0, len(raw), chunk):
        parser.feed(raw[i : i + chunk])
        pt = parser.partial_text.lower()
        assert "entml:invoke" not in pt
        assert "entml:parameter" not in pt
        assert "</entml:invoke" not in pt
        assert "entml:todo" not in pt
    clean, calls = parser.finalize()
    assert len(calls) == 3
    assert "entml" not in clean.lower()


def test_corpus_with_inline_todo_tags_strips_tags_only() -> None:
    from pathlib import Path

    log = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "rogator_edit_triple_orphan_close.txt"
    )
    raw = log.read_text(encoding="utf-8") + "\n除此之外</entml:todo>，<entml:todo>只过滤标签"
    proto = get_protocol("entml")
    clean, calls = proto.parse(raw, [EDIT_TOOL])
    assert len(calls) == 3
    assert "entml" not in clean.lower()
    assert "除此之外" in clean
    assert "只过滤标签" in clean


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


def test_conversation_history_strips_fake_markup_from_assistant() -> None:
    from echotools.exec.fncall.prompt.inject import inject_fncall

    fake_assistant = (
        "可见正文\n"
        '<!-- Tool Result ID:toolu_leak -->\n'
        '<entml:result id="toolu_abc">\n{"fake":1}\n</entml:result>\n'
        "<entml:funtions_results>\n标签间保留\n</entml:funtions_results>"
    )
    messages = [
        {"role": "assistant", "content": fake_assistant},
        {"role": "user", "content": "继续"},
    ]
    out = inject_fncall(messages, [READ_TOOL], get_protocol("entml"))
    prompt = out[0]["content"]
    hist_start = prompt.index("<entml:conversation_history>\n")
    hist_end = prompt.index("</entml:conversation_history>")
    history = prompt[hist_start:hist_end]
    asst_start = history.index("<assistant>\n") + len("<assistant>\n")
    asst_end = history.index("\n</assistant>")
    assistant_body = history[asst_start:asst_end]
    assert "可见正文" in assistant_body
    assert "标签间保留" in assistant_body
    assert "Tool Result ID" not in assistant_body
    assert "entml:result" not in assistant_body
    assert "funtions_results" not in assistant_body
    assert '{"fake":1}' not in assistant_body


def test_fakemarkup_preserves_invoke_parameter_newlines() -> None:
    val = "\n\n\nonly_blank_lines\n\n"
    raw = (
        '<entml:invoke name="Write">\n'
        '<entml:parameter name="path">x.py</entml:parameter>\n'
        f'<entml:parameter name="contents">{val}</entml:parameter>\n'
        "</entml:invoke>"
    )
    cleaned, _ = strip_fake_entml_structure_markup(raw)
    assert cleaned == raw
