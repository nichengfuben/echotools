"""模拟模型 ``<entml:thinking>…</thinking>`` fault 容错输出（rogator / Claude Code 高发）。

非真实模型日志；用于 batch ``protocol.parse`` 与 ``FncallStreamParser`` 分流回归。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from fixtures.simulated_llm_tool_responses import AGENT_TOOLS, TOOLS, _TOOL_BY_NAME


@dataclass(frozen=True)
class FaultThinkingCase:
    """一条 fault ``</thinking>`` 模拟回复及 batch/stream 期望。"""

    id: str
    description: str
    response: str
    extra_tools: Tuple[str, ...] = ()
    expect_names: Tuple[str, ...] = ()
    expect_args: Tuple[Dict[str, Any], ...] = ()
    expect_call_count: Optional[int] = None
    expect_thinking_contains: Tuple[str, ...] = ()
    expect_clean_contains: Tuple[str, ...] = ()
    expect_clean_absent: Tuple[str, ...] = ("entml:invoke", "entml:parameter")
    expect_clean_excludes: Tuple[str, ...] = ()
    expect_split_thinking_contains: Tuple[str, ...] = ()
    expect_split_thinking_empty: bool = False
    chunk_sizes: Tuple[int, ...] = (1, 3, 5, 8, 17, 64)
    worst_split: bool = False


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

_EXTRA_BY_NAME: Dict[str, Dict[str, Any]] = {
    **_TOOL_BY_NAME,
    "Read": READ_TOOL,
}


def tools_for_fault_case(case: FaultThinkingCase) -> List[Dict[str, Any]]:
    names = {t["function"]["name"] for t in TOOLS}
    out = list(TOOLS)
    for name in case.extra_tools:
        if name not in names and name in _EXTRA_BY_NAME:
            out.append(_EXTRA_BY_NAME[name])
            names.add(name)
    return out


def _big_bash_body() -> str:
    script = "python -c \"print('ok')\"" + ";" + "echo " + ("x" * 6800)
    return (
        "<entml:thinking>\n"
        "用户要求执行较长 shell；我先确认不会破坏环境，再用 Bash。\n"
        "</thinking>\n"
        '<entml:invoke name="Bash">\n'
        f'<entml:parameter name="command">{script}</entml:parameter>\n'
        "</entml:invoke>"
    )


FAULT_THINKING_CASES: Tuple[FaultThinkingCase, ...] = (
    FaultThinkingCase(
        id="model_fault_read_after_close",
        description="rogator 高发：中文思考 + </thinking> + 说明 + Read",
        extra_tools=("Read",),
        response=(
            "<entml:thinking>\n"
            "用户希望查看 main.py。我先确认路径，再调用 Read。\n"
            "</thinking>\n"
            "我先读取该文件。\n"
            '<entml:invoke name="Read">\n'
            '<entml:parameter name="path">src/main.py</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=("Read",),
        expect_args=({"path": "src/main.py"},),
        expect_thinking_contains=("main.py", "Read"),
        expect_clean_contains=("我先读取该文件。",),
        expect_split_thinking_contains=("main.py",),
        worst_split=True,
    ),
    FaultThinkingCase(
        id="model_fault_bash_git_status",
        description="英文思考 + </thinking> 后直接 Bash（无中间正文）",
        extra_tools=("Bash",),
        response=(
            "<entml:thinking>\n"
            "Need to inspect the working tree before answering.\n"
            "</thinking>\n"
            '<entml:invoke name="Bash">\n'
            '<entml:parameter name="command">git status --short</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=("Bash",),
        expect_args=({"command": "git status --short"},),
        expect_thinking_contains=("working tree",),
        expect_split_thinking_contains=("working tree",),
    ),
    FaultThinkingCase(
        id="model_fault_weather_with_visible",
        description="fault 闭合后先可见说明再 get_weather",
        response=(
            "<entml:thinking>\n"
            "用户问杭州天气，我需要调用 get_weather。\n"
            "</thinking>\n"
            "正在查询杭州天气。\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            '<entml:parameter name="unit">c</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=("get_weather",),
        expect_args=({"city": "杭州", "unit": "c"},),
        expect_thinking_contains=("杭州",),
        expect_clean_contains=("正在查询杭州天气。",),
        expect_split_thinking_contains=("杭州",),
    ),
    FaultThinkingCase(
        id="model_fault_read_then_bash",
        description="</thinking> 后连续 Read + Bash（双工具）",
        extra_tools=("Read", "Bash"),
        response=(
            "<entml:thinking>\n"
            "先读配置，再跑脚本验证。\n"
            "</thinking>\n"
            '<entml:invoke name="Read">\n'
            '<entml:parameter name="path">config.toml</entml:parameter>\n'
            "</entml:invoke>\n"
            '<entml:invoke name="Bash">\n'
            '<entml:parameter name="command">python verify.py</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=("Read", "Bash"),
        expect_args=({"path": "config.toml"}, {"command": "python verify.py"}),
        expect_thinking_contains=("先读配置",),
        expect_split_thinking_contains=("先读配置",),
    ),
    FaultThinkingCase(
        id="model_fault_close_without_invoke",
        description="</thinking> 后无 invoke，直到标准 </entml:thinking> 才结束",
        response=(
            "<entml:thinking>\n"
            "模型有时会在正文里提到 </thinking> 标签本身。\n"
            "</thinking>\n"
            "继续推理，尚未调用工具。\n"
            "</entml:thinking>\n"
            "这是给用户的最终回答。"
        ),
        expect_call_count=0,
        expect_thinking_contains=("提到", "继续推理"),
        expect_clean_contains=("最终回答",),
        expect_split_thinking_contains=("</thinking>", "继续推理"),
    ),
    FaultThinkingCase(
        id="model_invoke_inside_before_fault_close",
        description="错误：invoke 写在 </thinking> 之前，不得解析",
        extra_tools=("Bash",),
        response=(
            "<entml:thinking>\n"
            "我先尝试调用 Bash：\n"
            '<entml:invoke name="Bash">\n'
            '<entml:parameter name="command">echo oops</entml:parameter>\n'
            "</entml:invoke>\n"
            "</thinking>\n"
            "以上是思考过程，现在开始正式回复。"
        ),
        expect_call_count=0,
        expect_thinking_contains=("echo oops", "正式回复"),
        expect_clean_excludes=("正式回复", "echo oops"),
        expect_split_thinking_empty=True,
    ),
    FaultThinkingCase(
        id="model_fault_large_bash",
        description="rogator 7KB 级 Bash：fault 闭合后长 parameter",
        extra_tools=("Bash",),
        response=_big_bash_body(),
        expect_names=("Bash",),
        expect_thinking_contains=("较长 shell",),
        expect_split_thinking_contains=("较长 shell",),
        chunk_sizes=(1, 8, 17, 64),
    ),
    FaultThinkingCase(
        id="model_fault_multiline_parameter_read",
        description="</thinking> 与 invoke/parameter 之间有额外空行",
        extra_tools=("Read",),
        response=(
            "<entml:thinking>\n"
            "Read C:/tmp/x.py\n"
            "</thinking>\n"
            "\n"
            '<entml:invoke name="Read">\n'
            '\n'
            '<entml:parameter name="path">C:/tmp/x.py</entml:parameter>\n'
            "\n"
            "</entml:invoke>"
        ),
        expect_names=("Read",),
        expect_args=({"path": "C:/tmp/x.py"},),
        expect_thinking_contains=("Read C:/tmp/x.py",),
        worst_split=True,
    ),
)


def iter_fault_thinking_cases() -> List[FaultThinkingCase]:
    return list(FAULT_THINKING_CASES)
