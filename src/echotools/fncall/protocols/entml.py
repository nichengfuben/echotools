"""Entropy ML (entml) (entml) 协议实现。

使用 <entml:function_calls> 作为触发标记，
<entml:invoke name="..."> 作为调用格式。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_CLARIFY_ZH,
)
from echotools.fncall.shared.coercion import (
    _build_param_schema_index,
    _coerce_param_value,
)
from echotools.fncall.shared.normalization import normalize_tool_calls
from echotools.logger.manager import get_logger
from echotools.protocol.base import ToolProtocol

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 硬编码 Prompt 指令
# ---------------------------------------------------------------------------

_ANTML_INSTRUCTION = """\
## Function Definitions

All functions are defined inside a `<functions>` wrapper block. Each function is a JSON object inside a `<function>` tag containing `description`, `name`, and `parameters` (JSON Schema).

**Function Invocation Syntax:**

When calling tools, respond with ONLY the following XML block format:

<entml:function_calls>
<entml:invoke name="tool_name">
<entml:parameters>
<param_name>value</param_name>
</entml:parameters>
</entml:invoke>
</entml:function_calls>

Multiple invocations can be stacked inside one `<entml:function_calls>` block for parallel execution.

## Function Call Instructions

When making function calls using tools that accept array or object parameters, ensure those are structured using JSON.

Answer the user's request using the relevant tool(s), if they are available. Check that all required parameters are provided or can reasonably be inferred from context. If there are no relevant tools or missing required parameter values, ask the user. If the user provides a specific value for a parameter (e.g., in quotes), use that value EXACTLY. Do NOT make up values for or ask about optional parameters.

If you intend to call multiple tools and there are no dependencies between the calls, make all independent calls in the same function_calls block. Otherwise, wait for previous calls to finish to determine dependent values (do NOT use placeholders or guess missing parameters).
"""

# ---------------------------------------------------------------------------
# 正则常量
# ---------------------------------------------------------------------------

_BLOCK_RE = re.compile(
    r"<entml:function_calls\b[^>]*>([\s\S]*?)</entml:function_calls>",
    re.DOTALL,
)
_INVOKE_RE = re.compile(
    r'<entml:invoke\s+name="([^"]+)">\s*([\s\S]*?)\s*</entml:invoke>',
    re.DOTALL,
)
_PARAM_RE = re.compile(
    r'<entml:parameter\s+name="([^"]+)">\s*([\s\S]*?)\s*</entml:parameter>',
    re.DOTALL,
)
_PARAMETERS_RE = re.compile(
    r'<entml:parameters>([\s\S]*?)</entml:parameters>',
    re.DOTALL,
)
# 用于解析 <entml:parameters> 内的子标签
_SUB_TAG_RE = re.compile(
    r'<([^>]+)>([\s\S]*?)</\1>',
    re.DOTALL,
)


def _parse_sub_tags(content: str, schema_index: Optional[Dict[str, Any]] = None, func_name: str = "") -> Dict[str, Any]:
    """解析 <entml:parameters> 内的子标签，返回参数字典。"""
    args: Dict[str, Any] = {}
    for m in _SUB_TAG_RE.finditer(content):
        pname = m.group(1).strip()
        pval = m.group(2).strip()
        pschema = schema_index.get(func_name, {}).get(pname, {}) if schema_index else {}
        if pschema:
            args[pname] = _coerce_param_value(pval, pschema)
        else:
            try:
                args[pname] = json.loads(pval)
            except json.JSONDecodeError:
                args[pname] = pval
    return args


# ---------------------------------------------------------------------------
# Entml 协议
# ---------------------------------------------------------------------------


class EntmlProtocol(ToolProtocol):
    """Entropy ML (entml) 格式工具调用协议适配器。

    使用 <entml:function_calls><entml:invoke name="...">...</entml:invoke>
    作为触发标记和调用格式。
    """

    @property
    def id(self) -> str:
        return "entml"

    _TRIGGER = "<entml:function_calls>"
    _END_TAG = "</entml:function_calls>"

    def get_trigger_tags(self) -> List[str]:
        return [self._TRIGGER]

    def render_prompt(
        self,
        tool_descs: str,
        lang: str,
        user_system_prompt: str = "",
        history_text: str = "",
        loop_warning: str = "",
        current_user_message: str = "",
    ) -> str:
        """构建完整的 prompt 字符串，注入工具定义。"""
        sections: List[str] = [_ANTML_INSTRUCTION]

        # Add tool definitions in a functions block
        sections.append("<functions>\n" + tool_descs + "\n</functions>")

        if user_system_prompt and user_system_prompt.strip():
            sections.append(
                f"<user_system_prompt>\n{user_system_prompt.strip()}\n</user_system_prompt>"
            )

        if history_text:
            clarify = _HISTORY_CLARIFY_ZH if lang == "zh" else _HISTORY_CLARIFY_EN
            sections.append(f"<conversation_history>\n{clarify}\n\n{history_text}\n</conversation_history>")

        if loop_warning:
            sections.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")

        if current_user_message:
            sections.append(
                f"<current_user_message>\n{current_user_message}\n</current_user_message>"
            )
        else:
            sections.append("<current_user_message>\n</current_user_message>")

        prompt = "\n\n".join(sections)

        return prompt

    _TRIGGER_PREFIX = "<entml:function_calls"

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        """检测 buffer 中是否包含 ``<entml:function_calls...>`` 触发标记。

        容忍变体（如 ``<entml:function_calls >`` 或带属性），只要前缀
        ``<entml:function_calls`` 后跟任意字符并以 ``>`` 闭合即视为触发。
        """
        pos = buffer.find(self._TRIGGER_PREFIX)
        if pos < 0:
            return (False, -1)
        close = buffer.find(">", pos + len(self._TRIGGER_PREFIX))
        if close < 0:
            # 标签未闭合：视为待流入的增量
            return (False, -1)
        return (True, pos)

    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """从文本中提取工具调用，返回 (清理后文本, tool_calls 列表)。"""
        tool_calls: List[Dict[str, Any]] = []
        schema_index: Optional[Dict[str, Any]] = None

        for block_m in _BLOCK_RE.finditer(text):
            block_body = block_m.group(1)

            # Build schema index lazily on first invocation
            if schema_index is None and tools is not None:
                schema_index = _build_param_schema_index(tools)

            for invoke_m in _INVOKE_RE.finditer(block_body):
                name = invoke_m.group(1).strip()
                body = invoke_m.group(2)

                # Extract parameters - support both <entml:parameter> and <entml:parameters>
                args: Dict[str, Any] = {}

                # Try <entml:parameters>{json}</entml:parameters> format first
                params_m = _PARAMETERS_RE.search(body)
                if params_m:
                    params_content = params_m.group(1).strip()
                    try:
                        # 尝试 JSON 解析
                        args = json.loads(params_content)
                        if not isinstance(args, dict):
                            args = {"value": args}
                    except json.JSONDecodeError:
                        # 不是 JSON，尝试解析子标签
                        args = _parse_sub_tags(params_content, schema_index, name)
                        # 如果子标签解析也没结果，整个当作值
                        if not args:
                            args = {"value": params_content}
                else:
                    # Try <entml:parameter name="...">value</entml:parameter> format
                    for param_m in _PARAM_RE.finditer(body):
                        pname = param_m.group(1).strip()
                        pval = param_m.group(2).strip()
                        pschema = (
                            schema_index.get(name, {}).get(pname, {})
                            if schema_index
                            else {}
                        )
                        if pschema:
                            args[pname] = _coerce_param_value(pval, pschema)
                        else:
                            try:
                                args[pname] = json.loads(pval)
                            except json.JSONDecodeError:
                                args[pname] = pval

                arguments = json.dumps(args, ensure_ascii=False)
                tool_calls.append(
                    {
                        "id": f"call_{len(tool_calls):04d}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                )

        clean = text
        if tool_calls:
            clean = _BLOCK_RE.sub("", text).strip()

        return (clean, normalize_tool_calls(tool_calls, tools))

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """将已知的完整 entml 片段直接解析为 tool_calls 列表。"""
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content: str) -> str:
        """从响应文本中移除 <entml:function_calls> 标签残留。"""
        return _BLOCK_RE.sub("", content).strip()

    def format_assistant_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> str:
        """将 tool_call 对象列表渲染为 entml 格式。"""
        if not tool_calls:
            return ""

        parts: List[str] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", "{}")
            parts.append(
                f'<entml:invoke name="{name}">'
                f"<entml:parameters>{args}</entml:parameters>"
                f"</entml:invoke>"
            )
        return f"<entml:function_calls>{''.join(parts)}</entml:function_calls>"

    def supports_streaming(self) -> bool:
        """entml 协议支持流式检测。"""
        return True
