"""XML 协议实现。

使用 <|PROVIDER| 命名空间的 managed XML 格式。
同时支持旧版 <function_calls> 格式作为回退。
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
from echotools.fncall.shared.xml_helpers import (
    _PROVIDER_BLOCK_RE,
    _PROVIDER_INVOKE_RE,
    _PROVIDER_PARAM_RE,
    _PROVIDER_START,
    _PROVIDER_END,
    extract_cdata,
    escape_xml_attr,
)


# ---------------------------------------------------------------------------
# XML 协议
# ---------------------------------------------------------------------------

# 旧版 <function_calls> 格式（回退兼容）
_XML_START = "<tool_calls>"
_FNCALL_TAG_RE = re.compile(r"<function_calls>", re.DOTALL)
_FUNC_CALLS_RE = re.compile(r"<function_calls>.*?</function_calls>", re.DOTALL)


class XmlProtocol(ToolProtocol):
    """XML 格式工具调用协议适配器。

    优先使用 <|PROVIDER|tool_calls> 格式，同时回退支持旧版 <function_calls> 格式。
    """

    @property
    def id(self) -> str:
        return "xml"

    def get_trigger_tags(self) -> List[str]:
        return [_PROVIDER_START, _XML_START, "<function_calls>"]

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

        使用 <|PROVIDER| 命名空间的 managed XML 格式。
        """
        instruction = f"""## Available Tools
You can invoke the following developer tools. Tool names are case-sensitive.
Use only the exact tool names listed below. Do not rename, camelCase, translate, shorten, or invent tool names.

{tool_descs}

When calling tools, respond with only this XML block:

{_PROVIDER_START}<|PROVIDER|invoke name="exact_tool_name"><|PROVIDER|parameter name="argument"><![CDATA[value]]></|PROVIDER|parameter></|PROVIDER|invoke>{_PROVIDER_END}

Tool results will be provided as XML result blocks:

<|PROVIDER|tool_result tool_call_id="call_id"><![CDATA[result]]></|PROVIDER|tool_result>"""

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
        for marker in [_PROVIDER_START, _XML_START, "<function_calls>"]:
            pos = buffer.find(marker)
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

        # 1. <|PROVIDER| 格式
        for block_m in _PROVIDER_BLOCK_RE.finditer(text):
            raw_matches.append(block_m.group(0))
            block_body = block_m.group(1)
            for inv_m in _PROVIDER_INVOKE_RE.finditer(block_body):
                func_name = inv_m.group(1).strip()
                body = inv_m.group(2)
                arguments = self._parse_managed_xml_params(body, func_name, tools)
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                })

        # 2. 旧版 <tool_calls> 和 <function_calls> 格式回退
        if not tool_calls:
            clean, calls = self._parse_legacy(text, tools)
            tool_calls = calls
            if tool_calls:
                raw_matches.append("legacy")

        clean = text
        if tool_calls:
            for raw in raw_matches:
                if raw != "legacy":
                    clean = clean.replace(raw, "", 1)
            clean = _FUNC_CALLS_RE.sub("", clean)
            clean = clean.strip()

        return clean, tool_calls

    def _parse_managed_xml_params(
        self,
        body: str,
        func_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """解析 <|PROVIDER|parameter> 标签为 JSON 参数。"""
        result: Dict[str, Any] = {}
        schema_index = _build_param_schema_index(tools) if tools else None
        param_schemas: Dict[str, Dict[str, Any]] = {}
        if schema_index and func_name:
            param_schemas = schema_index.get(func_name) or {}

        for pm in _PROVIDER_PARAM_RE.finditer(body):
            key = pm.group(1).strip()
            val = extract_cdata(pm.group(2))
            pschema = param_schemas.get(key) or {}
            if pschema:
                result[key] = _coerce_param_value(val, pschema)
            else:
                try:
                    result[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    result[key] = val

        return json.dumps(result, ensure_ascii=False) if result else "{}"

    def _parse_legacy(
        self,
        text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """回退到旧版 parse_fncall 解析。"""
        from echotools.fncall.parsers.xml_parser import parse_fncall
        return parse_fncall(text, tools=tools)

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """将已知的 XML 片段直接解析为 tool_calls 列表。"""
        tool_calls: List[Dict[str, Any]] = []

        # 尝试 <|PROVIDER| 格式
        for block_m in _PROVIDER_BLOCK_RE.finditer(fragment):
            block_body = block_m.group(1)
            for inv_m in _PROVIDER_INVOKE_RE.finditer(block_body):
                func_name = inv_m.group(1).strip()
                body = inv_m.group(2)
                arguments = self._parse_managed_xml_params(body, func_name, tools)
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                })

        # 回退
        if not tool_calls:
            from echotools.fncall.parsers.xml_parser import parse_fncall_xml
            tool_calls = parse_fncall_xml(fragment, tools=tools)

        return tool_calls

    def clean_tags(self, content: str) -> str:
        """从响应文本中移除 XML 标签残留。"""
        cleaned = _PROVIDER_BLOCK_RE.sub("", content)
        cleaned = _FUNC_CALLS_RE.sub("", cleaned)
        return cleaned.strip()

    def format_assistant_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> str:
        """将 tool_call 对象列表渲染为 <|PROVIDER| XML 格式。"""
        if not tool_calls:
            return ""

        invokes = []
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
                params += f'<|PROVIDER|parameter name="{escape_xml_attr(pname)}"><![CDATA[{text_val}]]></|PROVIDER|parameter>'

            invokes.append(f'<|PROVIDER|invoke name="{escape_xml_attr(name)}">{params}</|PROVIDER|invoke>')

        return f"{_PROVIDER_START}{''.join(invokes)}{_PROVIDER_END}"

    def format_tool_result(
        self,
        content: str,
        tool_name: str = "",
        is_error: bool = False,
        tool_call_id: str = "",
    ) -> str:
        """将工具执行结果渲染为 <|PROVIDER| XML 格式。"""
        return f'<|PROVIDER|tool_result tool_call_id="{escape_xml_attr(tool_call_id)}"><![CDATA[{content}]]></|PROVIDER|tool_result>'

    def supports_streaming(self) -> bool:
        """XML 协议支持流式检测。"""
        return True
