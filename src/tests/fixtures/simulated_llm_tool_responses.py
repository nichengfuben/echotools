"""模拟 LLM 工具调用响应语料（非真实模型输出，仅用于解析回归）。

覆盖常见模型写法：thinking 前置、function_calls 外壳、属性乱序、
单双引号、markdown 围栏、转义下划线、并行多工具、JSON parameters、
type 注解、中英混排、正文夹杂等。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SimulatedCase:
    """一条模拟 LLM 完整回复及其期望解析结果。"""

    id: str
    description: str
    response: str
    expect_names: List[str]
    expect_args: List[Dict[str, Any]]
    expect_clean_substrings: List[str] = field(default_factory=list)
    expect_clean_absent: List[str] = field(default_factory=lambda: ["entml:invoke", "entml:parameter", "entml:function_calls"])
    expect_thinking: Optional[str] = None
    # 若为 False，表示本条允许解析失败（仍不得标签泄露）
    expect_success: bool = True


TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Query weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "unit": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Web search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "filters": {"type": "object"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run shell",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_ms": {"type": "integer"},
                    "env": {"type": "object"},
                },
                "required": ["command"],
            },
        },
    },
]


SIMULATED_LLM_RESPONSES: List[SimulatedCase] = [
    SimulatedCase(
        id="canonical_bare_invoke",
        description="规范裸 invoke，无 thinking",
        response=(
            "我先查一下杭州天气。\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            '<entml:parameter name="unit">c</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "杭州", "unit": "c"}],
        expect_clean_substrings=["我先查一下杭州天气。"],
    ),
    SimulatedCase(
        id="thinking_then_wrapper",
        description="thinking + function_calls 外壳（最常见线上形态）",
        response=(
            "<entml:thinking>\n"
            "用户要杭州天气，应调用 get_weather，unit 用 c。\n"
            "</entml:thinking>\n"
            "好的，我来查询。\n"
            "<entml:function_calls>\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            '<entml:parameter name="days">3</entml:parameter>\n'
            "</entml:invoke>\n"
            "</entml:function_calls>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "杭州", "days": 3}],
        expect_clean_substrings=["好的，我来查询。"],
        expect_thinking="用户要杭州天气，应调用 get_weather，unit 用 c。",
    ),
    SimulatedCase(
        id="parallel_two_tools",
        description="同一回复并行两个工具",
        response=(
            "<entml:thinking>\n并行查天气和搜索景点。\n</entml:thinking>\n"
            "稍等，我同时查天气和景点。\n"
            "<entml:function_calls>\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            "</entml:invoke>\n"
            '<entml:invoke name="search_web">\n'
            '<entml:parameter name="query">杭州西湖 周边景点</entml:parameter>\n'
            '<entml:parameter name="limit">5</entml:parameter>\n'
            "</entml:invoke>\n"
            "</entml:function_calls>"
        ),
        expect_names=["get_weather", "search_web"],
        expect_args=[
            {"city": "杭州"},
            {"query": "杭州西湖 周边景点", "limit": 5},
        ],
        expect_clean_substrings=["稍等，我同时查天气和景点。"],
        expect_thinking="并行查天气和搜索景点。",
    ),
    SimulatedCase(
        id="type_attrs_reordered",
        description="模型常把 type 写在 name 前，并混用 int/str",
        response=(
            "检索中。\n"
            '<entml:invoke name="search_web">\n'
            '<entml:parameter type="str" name="query">上海 降雨 预报</entml:parameter>\n'
            '<entml:parameter type="int" name="limit">3</entml:parameter>\n'
            '<entml:parameter name="tags" type="array">["weather","shanghai"]</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["search_web"],
        expect_args=[
            {
                "query": "上海 降雨 预报",
                "limit": 3,
                "tags": ["weather", "shanghai"],
            }
        ],
        expect_clean_substrings=["检索中。"],
    ),
    SimulatedCase(
        id="single_quotes_everywhere",
        description="整段单引号属性（部分模型/转义产物）",
        response=(
            "调用工具：\n"
            "<entml:invoke name='get_weather'>\n"
            "<entml:parameter name='city'>北京</entml:parameter>\n"
            "<entml:parameter name='unit'>c</entml:parameter>\n"
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "北京", "unit": "c"}],
        expect_clean_substrings=["调用工具："],
    ),
    SimulatedCase(
        id="markdown_fenced_xml",
        description="把 invoke 包进 ```xml 代码块",
        response=(
            "按规范调用：\n"
            "```xml\n"
            '<entml:invoke name="read_file">\n'
            '<entml:parameter name="path">src/main.py</entml:parameter>\n'
            '<entml:parameter name="offset">0</entml:parameter>\n'
            '<entml:parameter name="limit">80</entml:parameter>\n'
            "</entml:invoke>\n"
            "```"
        ),
        expect_names=["read_file"],
        expect_args=[{"path": "src/main.py", "offset": 0, "limit": 80}],
        expect_clean_substrings=["按规范调用："],
        expect_clean_absent=["entml:invoke", "entml:parameter", "```"],
    ),
    SimulatedCase(
        id="escaped_underscore_name",
        description="markdown 转义工具名 get\\_weather",
        response=(
            '<entml:invoke name="get\\_weather">\n'
            '<entml:parameter name="city">深圳</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "深圳"}],
    ),
    SimulatedCase(
        id="extra_attrs_on_invoke",
        description="invoke 带多余 id/index 属性",
        response=(
            '<entml:invoke name="search_web" id="call_1" index="0">\n'
            '<entml:parameter name="query">echotools sdk</entml:parameter>\n'
            '<entml:parameter name="limit">2</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["search_web"],
        expect_args=[{"query": "echotools sdk", "limit": 2}],
    ),
    SimulatedCase(
        id="parameters_json_block",
        description="使用 entml:parameters JSON 整包",
        response=(
            "执行搜索。\n"
            '<entml:invoke name="search_web">\n'
            "<entml:parameters>\n"
            '{"query":"西湖门票","limit":4,"tags":["travel"],"filters":{"lang":"zh"}}\n'
            "</entml:parameters>\n"
            "</entml:invoke>"
        ),
        expect_names=["search_web"],
        expect_args=[
            {
                "query": "西湖门票",
                "limit": 4,
                "tags": ["travel"],
                "filters": {"lang": "zh"},
            }
        ],
        expect_clean_substrings=["执行搜索。"],
    ),
    SimulatedCase(
        id="parameters_sub_tags_fallback",
        description="parameters 内非 JSON，回退子标签",
        response=(
            '<entml:invoke name="get_weather">\n'
            "<entml:parameters>\n"
            "<city>成都</city>\n"
            "<unit>c</unit>\n"
            "<days>2</days>\n"
            "</entml:parameters>\n"
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "成都", "unit": "c", "days": 2}],
    ),
    SimulatedCase(
        id="multiline_shell_command",
        description="多行命令参数 + 对象 env",
        response=(
            "<entml:thinking>\n需要跑一段检查脚本。\n</entml:thinking>\n"
            "我先跑检查。\n"
            '<entml:invoke name="run_shell">\n'
            '<entml:parameter name="command">\n'
            "python -m pytest src/tests -q\n"
            "</entml:parameter>\n"
            '<entml:parameter name="timeout_ms">60000</entml:parameter>\n'
            '<entml:parameter name="env">{"PYTHONPATH":"src","LANG":"C"}</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["run_shell"],
        expect_args=[
            {
                "command": "python -m pytest src/tests -q",
                "timeout_ms": 60000,
                "env": {"PYTHONPATH": "src", "LANG": "C"},
            }
        ],
        expect_clean_substrings=["我先跑检查。"],
        expect_thinking="需要跑一段检查脚本。",
    ),
    SimulatedCase(
        id="path_with_angle_brackets_noise",
        description="参数值含尖括号噪声",
        response=(
            '<entml:invoke name="read_file">\n'
            '<entml:parameter name="path">docs/<draft>.md</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["read_file"],
        expect_args=[{"path": "docs/<draft>.md"}],
    ),
    SimulatedCase(
        id="prose_then_tool_then_prose_attempt",
        description="工具前后都有可见正文",
        response=(
            "第一步先读文件。\n"
            '<entml:invoke name="read_file">\n'
            '<entml:parameter name="path">README.md</entml:parameter>\n'
            "</entml:invoke>\n"
            "读完再继续分析。"
        ),
        expect_names=["read_file"],
        expect_args=[{"path": "README.md"}],
        expect_clean_substrings=["第一步先读文件。", "读完再继续分析。"],
    ),
    SimulatedCase(
        id="only_thinking_no_tool",
        description="仅思考无工具——不得误解析",
        response=(
            "<entml:thinking>\n还需要用户确认城市。\n</entml:thinking>\n"
            "请问你要查哪个城市的天气？"
        ),
        expect_names=[],
        expect_args=[],
        expect_clean_substrings=["请问你要查哪个城市的天气？"],
        expect_thinking="还需要用户确认城市。",
        expect_success=True,
    ),
    SimulatedCase(
        id="orphan_close_tags_noise",
        description="模型胡写残留闭合标签，无有效 invoke",
        response=(
            "解析失败样例：</entml:invoke>\n"
            '<entml:parameter name="city">幽灵</entml:parameter>\n'
            "请重试。"
        ),
        expect_names=[],
        expect_args=[],
        expect_clean_substrings=["请重试。"],
        expect_success=True,
    ),
    SimulatedCase(
        id="three_tools_mixed_styles",
        description="三条调用混用不同写法",
        response=(
            "<entml:thinking>\n需要天气、搜索、读文件。\n</entml:thinking>\n"
            "开始。\n"
            "<entml:function_calls>\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">广州</entml:parameter>\n'
            "</entml:invoke>\n"
            '<entml:invoke name="search_web">\n'
            "<entml:parameters>"
            '{"query":"广州塔 开放时间","limit":1}'
            "</entml:parameters>\n"
            "</entml:invoke>\n"
            '<entml:invoke name="read\\_file">\n'
            '<entml:parameter type="str" name="path">notes.txt</entml:parameter>\n'
            "</entml:invoke>\n"
            "</entml:function_calls>"
        ),
        expect_names=["get_weather", "search_web", "read_file"],
        expect_args=[
            {"city": "广州"},
            {"query": "广州塔 开放时间", "limit": 1},
            {"path": "notes.txt"},
        ],
        expect_clean_substrings=["开始。"],
        expect_thinking="需要天气、搜索、读文件。",
    ),
    SimulatedCase(
        id="english_assistant_style",
        description="英文助手口吻 + wrapper",
        response=(
            "<entml:thinking>\nI should search the web for the SDK docs.\n</entml:thinking>\n"
            "I'll look that up.\n"
            "<entml:function_calls>\n"
            '<entml:invoke name="search_web">\n'
            '<entml:parameter name="query">echotools inject_fncall</entml:parameter>\n'
            '<entml:parameter name="limit">10</entml:parameter>\n'
            '<entml:parameter name="filters">{"site":"github.com"}</entml:parameter>\n'
            "</entml:invoke>\n"
            "</entml:function_calls>"
        ),
        expect_names=["search_web"],
        expect_args=[
            {
                "query": "echotools inject_fncall",
                "limit": 10,
                "filters": {"site": "github.com"},
            }
        ],
        expect_clean_substrings=["I'll look that up."],
        expect_thinking="I should search the web for the SDK docs.",
    ),
    SimulatedCase(
        id="boolean_like_strings_stay_string_when_schema_string",
        description="string 字段写入 true/false 字面量应保持语义正确",
        response=(
            '<entml:invoke name="search_web">\n'
            '<entml:parameter name="query">true</entml:parameter>\n'
            '<entml:parameter name="limit">1</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["search_web"],
        expect_args=[{"query": "true", "limit": 1}],
    ),
    SimulatedCase(
        id="dense_no_newlines",
        description="无换行压缩输出（部分模型）",
        response=(
            "查一下。"
            '<entml:invoke name="get_weather">'
            '<entml:parameter name="city">南京</entml:parameter>'
            '<entml:parameter name="days">1</entml:parameter>'
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "南京", "days": 1}],
        expect_clean_substrings=["查一下。"],
    ),
    SimulatedCase(
        id="history_style_tool_block_must_not_parse",
        description="历史 <tool> 伪代码不得被当成 invoke",
        response=(
            "参考历史：\n"
            "<tool>\n"
            "[get_weather: 杭州 | c]\n"
            "晴 26°C\n"
            "</tool>\n"
            "我再确认一次实时天气。\n"
            '<entml:invoke name="get_weather">\n'
            '<entml:parameter name="city">杭州</entml:parameter>\n'
            '<entml:parameter name="unit">c</entml:parameter>\n'
            "</entml:invoke>"
        ),
        expect_names=["get_weather"],
        expect_args=[{"city": "杭州", "unit": "c"}],
        expect_clean_substrings=["参考历史：", "[get_weather: 杭州 | c]", "我再确认一次实时天气。"],
    ),
]


def iter_simulated_cases():
    return list(SIMULATED_LLM_RESPONSES)
