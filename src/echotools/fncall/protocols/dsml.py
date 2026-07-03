"""DSML 协议实现。

使用 DSML 命名空间的 XML-like 格式进行工具调用。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.protocol.base import ToolProtocol
from echotools.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_CLARIFY_ZH,
)
from echotools.fncall.shared.coercion import _build_param_schema_index, _coerce_param_value
from echotools.fncall.shared.xml_helpers import escape_xml_attr


# ---------------------------------------------------------------------------
# DSML 协议
# ---------------------------------------------------------------------------

_DSML_START = "<｜｜DSML｜｜tool_calls>"
_DSML_END = "</｜｜DSML｜｜tool_calls>"

_DSML_BLOCK_RE = re.compile(
    r'<｜｜DSML｜｜tool_calls>([\s\S]*?)</｜｜DSML｜｜tool_calls>',
    re.DOTALL,
)
_DSML_CALL_RE = re.compile(
    r'<｜｜DSML｜｜tool_call>([\s\S]*?)</｜｜DSML｜｜tool_call>',
    re.DOTALL,
)
_DSML_NAME_RE = re.compile(
    r'<｜｜DSML｜｜tool_name>(.*?)</｜｜DSML｜｜tool_name>',
)
_DSML_PARAM_RE = re.compile(
    r'<｜｜DSML｜｜parameter\s+name="([^"]+)"\s*>([\s\S]*?)</｜｜DSML｜｜parameter>',
    re.DOTALL,
)


class DsmlProtocol(ToolProtocol):
    """DSML 格式工具调用协议适配器。"""

    @property
    def id(self) -> str:
        return "dsml"

    def get_trigger_tags(self) -> List[str]:
        return [_DSML_START]

    def render_prompt(
        self,
        tool_descs: str,
        lang: str,
        user_system_prompt: str = "",
        history_text: str = "",
        loop_warning: str = "",
        current_user_message: str = "",
    ) -> str:
        """构建完整的 prompt 字符串，注入工具定义。

        使用 DSML 格式。
        """
        instruction = f"""## Available Tools
You can invoke the following developer tools. Tool names are case-sensitive.
Use only the exact tool names listed below. Do not rename, camelCase, translate, shorten, or invent tool names.

{tool_descs}

When calling tools, respond with only this format:

{_DSML_START}
<｜｜DSML｜｜tool_call>
<｜｜DSML｜｜tool_name>exact_tool_name</｜｜DSML｜｜tool_name>
<｜｜DSML｜｜tool_parameters>
<｜｜DSML｜｜parameter name="argument">value</｜｜DSML｜｜parameter>
</｜｜DSML｜｜tool_parameters>
</｜｜DSML｜｜tool_call>
{_DSML_END}

Tool results will be provided as result blocks:

<｜｜DSML｜｜tool_result tool_call_id="call_id">result</｜｜DSML｜｜tool_result>"""

        sections = [instruction]
        if user_system_prompt and user_system_prompt.strip():
            sections.append(f"<user_system_prompt>\n{user_system_prompt.strip()}\n</user_system_prompt>")
        if history_text:
            clarify = _HISTORY_CLARIFY_ZH if lang == "zh" else _HISTORY_CLARIFY_EN
            sections.append(f"<conversation_history>\n{clarify}\n\n{history_text}\n</conversation_history>")
        if loop_warning:
            sections.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")
        if current_user_message:
            sections.append(f"<current_user_message>\n{current_user_message}\n</current_user_message>")

        return "\n\n".join(sections)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        """检测 buffer 中是否包含触发标记。"""
        pos = buffer.find(_DSML_START)
        if pos >= 0:
            return (True, pos)
        return (False, -1)

    def parse(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """从文本中提取工具调用，返回 (清理后文本, tool_calls 列表)。"""
        tool_calls: List[Dict[str, Any]] = []
        raw_matches: List[str] = []

        for block_m in _DSML_BLOCK_RE.finditer(text):
            raw_matches.append(block_m.group(0))
            block_body = block_m.group(1)
            for call_m in _DSML_CALL_RE.finditer(block_body):
                call_body = call_m.group(1)
                name_m = _DSML_NAME_RE.search(call_body)
                if not name_m:
                    continue
                func_name = name_m.group(1).strip()
                arguments = self._parse_dsml_params(call_body, func_name, tools)
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                })

        clean = text
        if tool_calls:
            for raw in raw_matches:
                clean = clean.replace(raw, "", 1)
            clean = clean.strip()

        return clean, tool_calls

    def _parse_dsml_params(
        self,
        call_body: str,
        func_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """解析 <｜｜DSML｜｜parameter> 标签为 JSON 参数。"""
        result: Dict[str, Any] = {}
        schema_index = _build_param_schema_index(tools) if tools else None
        param_schemas: Dict[str, Dict[str, Any]] = {}
        if schema_index and func_name:
            param_schemas = schema_index.get(func_name) or {}

        for pm in _DSML_PARAM_RE.finditer(call_body):
            key = pm.group(1).strip()
            val = pm.group(2).strip()
            pschema = param_schemas.get(key) or {}
            if pschema:
                result[key] = _coerce_param_value(val, pschema)
            else:
                try:
                    result[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    result[key] = val

        return json.dumps(result, ensure_ascii=False) if result else "{}"

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """将已知的 DSML 片段直接解析为 tool_calls 列表。"""
        tool_calls: List[Dict[str, Any]] = []

        for block_m in _DSML_BLOCK_RE.finditer(fragment):
            block_body = block_m.group(1)
            for call_m in _DSML_CALL_RE.finditer(block_body):
                call_body = call_m.group(1)
                name_m = _DSML_NAME_RE.search(call_body)
                if not name_m:
                    continue
                func_name = name_m.group(1).strip()
                arguments = self._parse_dsml_params(call_body, func_name, tools)
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                })

        return tool_calls

    def clean_tags(self, content: str) -> str:
        """从响应文本中移除 DSML 标签残留。"""
        cleaned = _DSML_BLOCK_RE.sub("", content)
        return cleaned.strip()

    def format_assistant_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> str:
        """将 tool_call 对象列表渲染为 DSML 格式。"""
        if not tool_calls:
            return ""

        calls = []
        for tc in tool_calls:
            name = tc.get("function", {}).get("name", "")
            args = tc.get("function", {}).get("arguments", "{}")
            try:
                args_dict = json.loads(args) if isinstance(args, str) else args
            except (json.JSONDecodeError, ValueError):
                args_dict = {}

            params = ""
            for pname, pval in args_dict.items():
                text_val = pval if isinstance(pval, str) else json.dumps(pval, ensure_ascii=False)
                params += f'<｜｜DSML｜｜parameter name="{escape_xml_attr(pname)}">{text_val}</｜｜DSML｜｜parameter>\n'

            calls.append(
                f"<｜｜DSML｜｜tool_call>\n"
                f"<｜｜DSML｜｜tool_name>{name}</｜｜DSML｜｜tool_name>\n"
                f"<｜｜DSML｜｜tool_parameters>\n{params}</｜｜DSML｜｜tool_parameters>\n"
                f"</｜｜DSML｜｜tool_call>"
            )

        return f"{_DSML_START}\n{''.join(calls)}\n{_DSML_END}"

    def format_tool_result(
        self,
        content: str,
        tool_name: str = "",
        is_error: bool = False,
        tool_call_id: str = "",
    ) -> str:
        """将工具执行结果渲染为 DSML 格式。"""
        return f'<｜｜DSML｜｜tool_result tool_call_id="{escape_xml_attr(tool_call_id)}">{content}</｜｜DSML｜｜tool_result>'

    def supports_streaming(self) -> bool:
        """DSML 协议支持流式检测。"""
        return True
