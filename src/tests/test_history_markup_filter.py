from __future__ import annotations

"""伪 ``<assistant>`` / ``<tool>`` history 标签：剥离、检测与注入 warning。"""

import pytest

from echotools.exec.fncall import get_protocol
from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.prompt.inject import inject_fncall
from echotools.exec.fncall.shared.history_markup import (
    detect_fake_history_markup,
    strip_fake_history_markup,
    strip_fake_history_markup_for_display,
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

REAL_INVOKE = (
    '<entml:invoke name="Read">\n'
    '<entml:parameter name="path">src/main.py</entml:parameter>\n'
    "</entml:invoke>"
)

USER_EDIT_MIMIC_RESPONSE = (
    "● 验证通过，无外部依赖残留。现在清理几个文件中遗留的旧路径注释。\n\n"
    "</thinking>\n\n"
    "<tool>\n"
    '{Edit: {"path": "X:/Project/Local/Provider-Deepseek-Adapter/provider_deepseek/core/protocol/consts.py", '
    '"old_string": "# src/old/path.py", "new_string": "x"}}\n'
    '{Edit: {"path": "X:/Project/Local/Provider-Deepseek-Adapter/provider_deepseek/core/protocol/headers.py", '
    '"old_string": "# old", "new_string": "y"}}\n'
    '{Edit: {"path": "X:/Project/Local/Provider-Deepseek-Adapter/provider_deepseek/core/__init__.py", '
    '"old_string": "from x", "new_string": "y"}}\n'
    "</tool>"
)

MODEL_MIMIC_RESPONSE = (
    "端点正确！HTTP 200，流式响应已启动。但响应内容为空——可能是响应解析问题或模型名称无效。\n\n"
    "需要：\n"
    "1. 添加调试日志查看服务器返回的实际帧内容\n"
    "2. 查找 ChatResponse 消息定义和有效模型名称\n\n"
    "<tool>\n"
    '{Read: {"file_path": "X:\\\\Project\\\\Extra\\\\260727\\\\cursor_agent_client.py", '
    '"offset": 485, "limit": 50}}\n'
    "485                       buf += chunk\n"
    "518                   return\n"
    "</tool>\n\n"
    "Excellent findings! ChatResponse fields include text.\n"
)


@pytest.mark.parametrize(
    "raw,expect_sub,expect_absent,expect_found",
    [
        (
            MODEL_MIMIC_RESPONSE,
            "端点正确",
            "<tool>",
            True,
        ),
        (
            "前言\n<assistant>\n不应可见\n</assistant>\n后缀",
            "前言",
            "不应可见",
            True,
        ),
        (
            "计划说明\n</assistant>\n后续仍可见",
            "后续仍可见",
            "计划说明",
            True,
        ),
        (
            "保留\n<tool>\n{Bash: echo}\n</tool>\n可见",
            "保留",
            "{Bash: echo}",
            True,
        ),
        (
            "<entml:thinking>\n讨论 <tool> 块格式\n</entml:thinking>\n"
            "真实可见回答",
            "讨论 <tool> 块格式",
            None,
            False,
        ),
        (
            "<entml:thinking>\nplan\n</entml:thinking>\n"
            "<tool>\n{Read: x}\n</tool>\n"
            "尾句",
            "plan",
            "{Read: x}",
            True,
        ),
        (
            USER_EDIT_MIMIC_RESPONSE,
            "验证通过",
            "Edit",
            True,
        ),
        (
            "可见正文\n</thinking>\n后续",
            "后续",
            "</thinking>",
            True,
        ),
        (
            "<thinking>\nplan\n</thinking>\nvisible",
            "visible",
            None,
            False,
        ),
    ],
)
def test_strip_fake_history_markup(
    raw: str,
    expect_sub: str,
    expect_absent: str | None,
    expect_found: bool,
) -> None:
    cleaned, found = strip_fake_history_markup(raw)
    assert found is expect_found
    assert expect_sub in cleaned
    if expect_absent:
        assert expect_absent not in cleaned


def test_strip_preserves_prose_mention_of_tool_word() -> None:
    text = "明白，不用 <tool> 块。现在用 entml invoke。"
    cleaned, found = strip_fake_history_markup(text)
    assert not found
    assert "<tool>" in cleaned


def test_display_strip_truncates_incomplete_fake_open() -> None:
    partial = "前言\n\n<tool"
    cleaned, found = strip_fake_history_markup_for_display(partial)
    assert found
    assert cleaned == "前言"
    partial2 = "前言\n\n<tool>\n{Edit: x"
    cleaned2, found2 = strip_fake_history_markup_for_display(partial2)
    assert found2
    assert cleaned2 == "前言"
    assert "Edit" not in cleaned2


class TestBatchParseFakeHistory:
    def test_batch_strips_fake_tool_block(self) -> None:
        proto = get_protocol("entml")
        clean, calls = proto.parse(MODEL_MIMIC_RESPONSE, [READ_TOOL])
        assert calls == []
        assert "<tool>" not in clean
        assert "485                       buf" not in clean
        assert "端点正确" in clean
        assert "Excellent findings" in clean

    def test_batch_real_invoke_outside_fake_block(self) -> None:
        text = f"说明。\n{REAL_INVOKE}"
        proto = get_protocol("entml")
        clean, calls = proto.parse(text, [READ_TOOL])
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "Read"
        assert "entml:invoke" not in clean


class TestStreamParseFakeHistory:
    @pytest.mark.parametrize("chunk", [1, 8, 17, 64])
    def test_stream_strips_fake_tool_block(self, chunk: int) -> None:
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
        for i in range(0, len(MODEL_MIMIC_RESPONSE), chunk):
            parser.feed(MODEL_MIMIC_RESPONSE[i : i + chunk])
        clean, calls = parser.finalize()
        assert calls == []
        assert "<tool>" not in clean
        assert "485                       buf" not in clean
        assert "端点正确" in clean

    @pytest.mark.parametrize("chunk", [1, 8, 17])
    def test_stream_orphan_assistant_close(self, chunk: int) -> None:
        text = "分析中...\n</assistant>\n后续仍可见"
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
        clean, _ = parser.finalize()
        assert "</assistant>" not in clean
        assert "分析中" not in clean
        assert "后续仍可见" in clean


class TestStreamPartialTextFakeHistory:
    """流式 ``partial_text`` 须在块闭合后即时剥离，不能等 finalize。"""

    @pytest.mark.parametrize("chunk", [1, 4, 8, 17, 64])
    def test_partial_text_hides_fake_tool_during_stream(self, chunk: int) -> None:
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
        leaked = False
        for i in range(0, len(USER_EDIT_MIMIC_RESPONSE), chunk):
            parser.feed(USER_EDIT_MIMIC_RESPONSE[i : i + chunk])
            pt = parser.partial_text
            if "<tool>" in pt or "Edit:" in pt or "Provider-Deepseek" in pt:
                leaked = True
        assert not leaked
        clean, calls = parser.finalize()
        assert calls == []
        assert "<tool>" not in clean
        assert "Edit" not in clean
        assert "验证通过" in clean

    @pytest.mark.parametrize("chunk", [1, 8, 32])
    def test_partial_text_model_mimic_no_leak(self, chunk: int) -> None:
        parser = FncallStreamParser(protocol=get_protocol("entml"), tools=[READ_TOOL])
        for i in range(0, len(MODEL_MIMIC_RESPONSE), chunk):
            parser.feed(MODEL_MIMIC_RESPONSE[i : i + chunk])
            pt = parser.partial_text
            assert "<tool>" not in pt
            assert "485                       buf" not in pt
        clean, calls = parser.finalize()
        assert calls == []
        assert "端点正确" in clean

    def test_batch_user_edit_mimic(self) -> None:
        proto = get_protocol("entml")
        clean, calls = proto.parse(USER_EDIT_MIMIC_RESPONSE, [READ_TOOL])
        assert calls == []
        assert "验证通过" in clean
        assert "<tool>" not in clean
        assert "Edit" not in clean
        assert "</thinking>" not in clean

    def test_fake_tool_then_real_invoke(self) -> None:
        text = f"{USER_EDIT_MIMIC_RESPONSE}\n\n说明。\n{REAL_INVOKE}"
        proto = get_protocol("entml")
        clean, calls = proto.parse(text, [READ_TOOL])
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "Read"
        assert "<tool>" not in clean
        assert "Edit" not in clean
        assert "说明" in clean

    @pytest.mark.parametrize("chunk", [1, 5, 17])
    def test_thinking_disabled_plain_open_finalize_preserves_visible(
        self, chunk: int
    ) -> None:
        """未开思考时 plain ``<thinking>`` 对不得因 orphan 剥离而清空 finalize。"""
        parser = FncallStreamParser(
            protocol=get_protocol("entml"),
            tools=[READ_TOOL],
            protocol_options={"thinking_mode": "off"},
        )
        text = "<thinking>\nplan\n</thinking>\nvisible\n"
        for i in range(0, len(text), chunk):
            parser.feed(text[i : i + chunk])
        clean, calls = parser.finalize()
        assert not calls
        assert "visible" in clean
        assert "<thinking>" in clean or "plan" in clean


class TestHistoryMarkupWarningInject:
    def test_detect_fake_markup_in_assistant_history(self) -> None:
        msgs = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": MODEL_MIMIC_RESPONSE},
        ]
        result = detect_fake_history_markup(msgs)
        assert result.detected
        assert "Do NOT output" in result.suggestion

    def test_inject_adds_history_markup_warning(self) -> None:
        msgs = [
            {"role": "user", "content": "first"},
            {
                "role": "assistant",
                "content": "ok\n<tool>\n{x: 1}\n</tool>",
                "tool_calls": [],
            },
            {"role": "user", "content": "next"},
        ]
        out = inject_fncall(
            msgs,
            tools=[READ_TOOL],
            protocol=get_protocol("entml"),
            loop_detection_threshold=0,
        )
        prompt = out[0]["content"]
        assert "<history_markup_warning>" in prompt
        assert "Do NOT output" in prompt
        idx_warn = prompt.index("<history_markup_warning>")
        idx_user = prompt.index("<current_user_message>")
        assert idx_warn < idx_user

    def test_render_prompt_section_order_with_both_warnings(self) -> None:
        proto = get_protocol("entml")
        prompt = proto.render_prompt(
            tool_descs=proto.format_tool_descs([READ_TOOL]),
            lang="en",
            loop_warning="loop!",
            history_markup_warning="markup!",
            current_user_message="now",
        )
        idx_loop = prompt.index("<loop_warning>")
        idx_markup = prompt.index("<history_markup_warning>")
        idx_user = prompt.index("<current_user_message>")
        assert idx_loop < idx_markup < idx_user
