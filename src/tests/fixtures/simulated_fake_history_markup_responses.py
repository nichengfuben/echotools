"""模拟模型误输出 conversation history 伪标签（``<assistant>`` / ``<tool>`` / orphan ``</thinking>``）。

非真实模型日志；用于 batch ``protocol.parse`` 与 ``FncallStreamParser`` 回归。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fixtures.simulated_llm_tool_responses import _TOOL_BY_NAME, TOOLS

READ_TOOL: Dict[str, Any] = {
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

EDIT_TOOL: Dict[str, Any] = {
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

_EXTRA_BY_NAME: Dict[str, Dict[str, Any]] = {
    **_TOOL_BY_NAME,
    "Read": READ_TOOL,
    "Edit": EDIT_TOOL,
}

DEFAULT_PARTIAL_LEAK_MARKERS: Tuple[str, ...] = (
    "<tool>",
    "</tool>",
    "<assistant>",
    "</assistant>",
    "{Edit:",
    "{Read:",
    "{Write:",
    "{Bash:",
)

REAL_READ_INVOKE = (
    '<entml:invoke name="Read">\n'
    '<entml:parameter name="path">src/main.py</entml:parameter>\n'
    "</entml:invoke>"
)

REAL_WEATHER_INVOKE = (
    '<entml:invoke name="get_weather">\n'
    '<entml:parameter name="city">杭州</entml:parameter>\n'
    '<entml:parameter name="unit">c</entml:parameter>\n'
    "</entml:invoke>"
)


@dataclass(frozen=True)
class HistoryMarkupCase:
    """一条伪 history 标签模拟回复及解析期望。"""

    id: str
    description: str
    response: str
    extra_tools: Tuple[str, ...] = ()
    expect_names: Tuple[str, ...] = ()
    expect_args: Tuple[Dict[str, Any], ...] = ()
    expect_call_count: int = 0
    expect_clean_contains: Tuple[str, ...] = ()
    expect_clean_absent: Tuple[str, ...] = (
        "entml:invoke",
        "entml:parameter",
        "<tool>",
        "</tool>",
        "<assistant>",
        "</assistant>",
    )
    expect_clean_excludes: Tuple[str, ...] = ()
    partial_leak_markers: Tuple[str, ...] = DEFAULT_PARTIAL_LEAK_MARKERS
    check_partial_text: bool = True
    thinking_mode: Optional[str] = None
    chunk_sizes: Tuple[int, ...] = (1, 3, 5, 8, 17, 64)
    worst_split: bool = False


def tools_for_markup_case(case: HistoryMarkupCase) -> List[Dict[str, Any]]:
    names = {t["function"]["name"] for t in TOOLS}
    out = list(TOOLS)
    for name in case.extra_tools:
        if name not in names and name in _EXTRA_BY_NAME:
            out.append(_EXTRA_BY_NAME[name])
            names.add(name)
    return out


FAKE_HISTORY_MARKUP_CASES: Tuple[HistoryMarkupCase, ...] = (
    HistoryMarkupCase(
        id="model_edit_mimic_orphan_thinking",
        description="Claude Code 高发：正文 + orphan </thinking> + 多块 Edit 伪 tool",
        extra_tools=("Read", "Edit"),
        response=(
            "● 验证通过，无外部依赖残留。现在清理几个文件中遗留的旧路径注释。\n\n"
            "</thinking>\n\n"
            "<tool>\n"
            '{Edit: {"path": "X:/Project/Local/foo/core/consts.py", '
            '"old_string": "# src/old/path.py", "new_string": "x"}}\n'
            '{Edit: {"path": "X:/Project/Local/foo/core/headers.py", '
            '"old_string": "# old", "new_string": "y"}}\n'
            '{Edit: {"path": "X:/Project/Local/foo/core/__init__.py", '
            '"old_string": "from x", "new_string": "y"}}\n'
            "</tool>"
        ),
        expect_clean_contains=("验证通过",),
        expect_clean_excludes=("Edit", "</thinking>"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="model_read_mimic_code_leak",
        description="模型把 Read 结果+源码行塞进伪 <tool> 块",
        extra_tools=("Read",),
        response=(
            "端点正确！HTTP 200，流式响应已启动。但响应内容为空。\n\n"
            "需要：\n"
            "1. 添加调试日志\n"
            "2. 查找 ChatResponse 定义\n\n"
            "<tool>\n"
            '{Read: {"file_path": "X:\\\\Project\\\\app\\\\client.py", '
            '"offset": 485, "limit": 50}}\n'
            "485                       buf += chunk\n"
            "518                   return\n"
            "</tool>\n\n"
            "Excellent findings! ChatResponse fields include text.\n"
        ),
        expect_clean_contains=("端点正确", "Excellent findings"),
        expect_clean_excludes=("485                       buf", "{Read:"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="fake_assistant_block",
        description="块级 <assistant> 包裹误输出正文",
        response=(
            "前言可见。\n"
            "<assistant>\n"
            "这是模型误写的 assistant 块\n"
            "</assistant>\n"
            "后缀仍可见。"
        ),
        expect_clean_contains=("前言可见", "后缀仍可见"),
        expect_clean_excludes=("误写的 assistant",),
    ),
    HistoryMarkupCase(
        id="orphan_assistant_close",
        description="无开标签的 </assistant> 反向闭合",
        response="分析中...\n</assistant>\n后续仍可见",
        expect_clean_contains=("后续仍可见",),
        expect_clean_excludes=("分析中", "</assistant>"),
    ),
    HistoryMarkupCase(
        id="fake_tool_bash_scalar",
        description="伪 tool 块内 {Bash: cmd} 标量行",
        extra_tools=("Bash",),
        response=(
            "保留。\n"
            "<tool>\n"
            "{Bash: echo hello}\n"
            "</tool>\n"
            "可见尾句。"
        ),
        expect_clean_contains=("保留", "可见尾句"),
        expect_clean_excludes=("{Bash:",),
    ),
    HistoryMarkupCase(
        id="thinking_discusses_tool_format",
        description="entml:thinking 内讨论 <tool> 格式不得剥离",
        response=(
            "<entml:thinking>\n"
            "history 注入用 <tool> 块展示已完成工具。\n"
            "</entml:thinking>\n"
            "真实可见回答。"
        ),
        expect_clean_contains=("真实可见回答",),
        expect_clean_absent=("entml:invoke", "entml:parameter"),
        partial_leak_markers=("{Read:", "{Edit:", "\n<tool>\n"),
        check_partial_text=False,
    ),
    HistoryMarkupCase(
        id="thinking_body_then_fake_tool",
        description="thinking 结束后 visible 区误输出伪 tool",
        response=(
            "<entml:thinking>\nplan\n</entml:thinking>\n"
            "<tool>\n{Read: x}\n</tool>\n"
            "尾句。"
        ),
        extra_tools=("Read",),
        expect_clean_contains=("尾句",),
        expect_clean_excludes=("{Read: x}",),
    ),
    HistoryMarkupCase(
        id="orphan_thinking_line_only",
        description="visible 区仅 orphan </thinking> 行",
        response="可见正文\n</thinking>\n后续",
        expect_clean_contains=("后续",),
        expect_clean_excludes=("</thinking>",),
    ),
    HistoryMarkupCase(
        id="fake_assistant_wraps_entml_thinking",
        description="误用 <assistant> 包裹 entml thinking（中文在 thinking 内）",
        response=(
            "<assistant>\n"
            "<entml:thinking>\n"
            "计划修改 consts.py。\n"
            "</thinking>\n"
            "中文说明仍在 thinking 内。\n"
            "</entml:thinking>\n"
            "</assistant>\n"
            "真实可见回复。"
        ),
        expect_clean_contains=("真实可见回复",),
        expect_clean_excludes=("<assistant>", "</assistant>"),
        partial_leak_markers=("<assistant>", "{Edit:"),
    ),
    HistoryMarkupCase(
        id="double_fake_tool_blocks",
        description="连续两个伪 tool 块",
        extra_tools=("Read", "Bash"),
        response=(
            "开始。\n"
            "<tool>\n{Read: a}\n</tool>\n"
            "中间。\n"
            "<tool>\n{Bash: ls}\n</tool>\n"
            "结束。"
        ),
        expect_clean_contains=("开始", "中间", "结束"),
        expect_clean_excludes=("{Read:", "{Bash:"),
    ),
    HistoryMarkupCase(
        id="fake_tool_then_real_read",
        description="伪 tool 块后接真实 entml invoke",
        extra_tools=("Read",),
        response=f"说明。\n<tool>\n{{Read: ghost}}\n</tool>\n\n{REAL_READ_INVOKE}",
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("说明",),
        expect_clean_excludes=("ghost", "<tool>"),
        partial_leak_markers=("<tool>", "ghost", "{Read: ghost"),
    ),
    HistoryMarkupCase(
        id="history_style_then_real_weather",
        description="历史 brace 伪 tool + 真实 get_weather invoke",
        response=(
            "参考历史：\n"
            "<tool>\n"
            '{get_weather: {"city": "杭州", "unit": "c"}}\n'
            "晴 26°C\n"
            "</tool>\n"
            "我再确认一次。\n"
            f"{REAL_WEATHER_INVOKE}"
        ),
        expect_names=("get_weather",),
        expect_args=({"city": "杭州", "unit": "c"},),
        expect_call_count=1,
        expect_clean_contains=("参考历史", "我再确认一次"),
        expect_clean_excludes=('{get_weather:', "26°C"),
        partial_leak_markers=("<tool>", "{get_weather:"),
    ),
    HistoryMarkupCase(
        id="fake_tool_orphan_open_no_close",
        description="仅 orphan 开标签 <tool> 无闭合",
        extra_tools=("Edit",),
        response="前言\n<tool>\n{Edit: x}\n后续不应可见",
        expect_clean_contains=("前言",),
        expect_clean_excludes=("后续不应可见", "{Edit:"),
    ),
    HistoryMarkupCase(
        id="assistant_then_tool_blocks",
        description="先 fake assistant 再 fake tool",
        response=(
            "<assistant>\nassistant 误块\n</assistant>\n"
            "<tool>\n{Write: out.txt}\n</tool>\n"
            "OK"
        ),
        extra_tools=("Write",),
        expect_clean_contains=("OK",),
        expect_clean_excludes=("assistant 误块", "{Write:"),
    ),
    HistoryMarkupCase(
        id="fault_thinking_close_then_fake_tool",
        description="entml thinking + fault </thinking> 后误写伪 tool 而非 invoke",
        extra_tools=("Read",),
        response=(
            "<entml:thinking>\n"
            "应先 Read 再总结。\n"
            "</thinking>\n"
            "</entml:thinking>\n"
            "<tool>\n"
            '{Read: {"path": "secret.py"}}\n'
            "</tool>\n"
            "以上是误输出。"
        ),
        expect_clean_contains=("以上是误输出",),
        expect_clean_excludes=("secret.py", "<tool>"),
        expect_names=("Read",),
        expect_args=({"path": "secret.py"},),
        expect_call_count=1,
    ),
    HistoryMarkupCase(
        id="plain_thinking_pair_thinking_off",
        description="thinking_mode=off 时 plain <thinking> 对保留",
        thinking_mode="off",
        response="<thinking>\nplan\n</thinking>\nvisible\n",
        expect_clean_contains=("visible",),
        partial_leak_markers=("<tool>", "{Edit:"),
        check_partial_text=True,
    ),
    HistoryMarkupCase(
        id="prose_mentions_tool_inline",
        description="行内 prose 提及 <tool> 不误伤",
        response="明白，不用 <tool> 块。现在用 entml invoke。",
        expect_clean_contains=("明白", "entml invoke"),
        expect_clean_absent=("entml:invoke", "entml:parameter", "<assistant>", "</assistant>"),
        partial_leak_markers=("{Read:", "{Edit:", "\n<tool>\n"),
    ),
    HistoryMarkupCase(
        id="edit_mimic_with_trailing_real_invoke",
        description="Edit 伪块 + 尾部真实 Read（用户报告形态扩展）",
        extra_tools=("Read", "Edit"),
        response=(
            "● 验证通过。\n\n"
            "</thinking>\n\n"
            "<tool>\n"
            '{Edit: {"path": "a.py", "old_string": "x", "new_string": "y"}}\n'
            "</tool>\n\n"
            f"{REAL_READ_INVOKE}"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("验证通过",),
        expect_clean_excludes=("Edit", "<tool>"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="unclosed_fake_tool_before_invoke",
        description="未闭合伪 <tool> 后直接写 entml:invoke，不得吞 invoke",
        extra_tools=("Read", "Edit"),
        response=(
            "说明。\n"
            "<tool>\n"
            '{Edit: {"path": "a.py", "old_string": "x", "new_string": "y"}}\n'
            f"{REAL_READ_INVOKE}"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("说明",),
        expect_clean_excludes=("Edit", "<tool>"),
        partial_leak_markers=("<tool>", "{Edit:", "entml:parameter"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="invoke_inside_closed_fake_tool",
        description="伪 <tool> 块内夹 entml:invoke，保留 invoke 剥离 brace",
        extra_tools=("Read", "Edit"),
        response=(
            "<tool>\n"
            '{Edit: {"path": "a.py"}}\n'
            f"{REAL_READ_INVOKE}\n"
            "</tool>\n"
            "尾句。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("尾句",),
        expect_clean_excludes=("Edit", "<tool>"),
        partial_leak_markers=("{Edit:", "\n<tool>\n"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="fake_tool_invoke_glued_no_newline",
        description="</tool> 与 <entml:invoke 粘连（分片边界）",
        extra_tools=("Read",),
        response=f"说明。\n<tool>\n{{Read: x}}\n</tool>{REAL_READ_INVOKE}",
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("说明",),
        expect_clean_excludes=("{Read: x}",),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="unclosed_fake_tool_invoke_trailing_reply",
        description="未闭合伪 <tool> + invoke + 可见尾句：batch/stream 均须保留尾句",
        extra_tools=("Read", "Edit"),
        response=(
            "前言\n"
            "<tool>\n"
            '{Edit: {"path": "a.py", "old_string": "x", "new_string": "y"}}\n'
            f"{REAL_READ_INVOKE}\n"
            "尾句保留。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("前言", "尾句保留"),
        expect_clean_excludes=("Edit", "<tool>"),
        partial_leak_markers=("<tool>", "{Edit:", "entml:parameter"),
        worst_split=True,
    ),
    HistoryMarkupCase(
        id="function_calls_wrap_trailing_reply",
        description="function_calls 包裹 invoke + 尾部可见回复",
        extra_tools=("Read",),
        response=(
            "说明。\n"
            "<entml:function_calls>\n"
            f"{REAL_READ_INVOKE}\n"
            "</entml:function_calls>\n"
            "后续说明。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("说明", "后续说明"),
        expect_clean_excludes=("<tool>",),
        partial_leak_markers=("<tool>", "{Edit:"),
    ),
    HistoryMarkupCase(
        id="invoke_then_fake_tool_then_reply",
        description="真实 invoke 后误写伪 tool，须剥离伪块保留尾句",
        extra_tools=("Read", "Edit"),
        response=(
            f"{REAL_READ_INVOKE}\n"
            "<tool>\n"
            '{Edit: {"path": "a.py"}}\n'
            "</tool>\n"
            "尾句。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("尾句",),
        expect_clean_excludes=("Edit", "<tool>"),
    ),
    HistoryMarkupCase(
        id="fake_tool_inside_function_calls_with_invoke",
        description="伪 <tool> 块内含 function_calls+invoke，不得误删 invoke",
        extra_tools=("Read", "Edit"),
        response=(
            "<tool>\n"
            '{Edit: {"path": "a.py"}}\n'
            "<entml:function_calls>\n"
            f"{REAL_READ_INVOKE}\n"
            "</entml:function_calls>\n"
            "</tool>\n"
            "尾句。"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_call_count=1,
        expect_clean_contains=("尾句",),
        expect_clean_excludes=("Edit", "<tool>"),
        worst_split=True,
    ),
)


def iter_fake_history_markup_cases() -> List[HistoryMarkupCase]:
    return list(FAKE_HISTORY_MARKUP_CASES)
