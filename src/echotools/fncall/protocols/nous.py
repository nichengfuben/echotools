"""Nous Research XML style tool invocation protocol."""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.protocol.base import ToolProtocol
from echotools.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_CLARIFY_ZH,
)
from echotools.fncall.shared.coercion import _build_param_schema_index, _coerce_param_value
from echotools.fncall.shared.normalization import format_tool_descs


# Regex patterns
_CDATA_RE = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.DOTALL)
_FC_BLOCK_RE = re.compile(r'<function_calls>([\s\S]*?)</function_calls>', re.DOTALL)
_INV_RE = re.compile(r'<invoke name="([^"]+)"\s*>([\s\S]*?)</invoke>', re.DOTALL)
_PARAM_RE = re.compile(r'<parameter name="([^"]+)"\s*>([\s\S]*?)</parameter>', re.DOTALL)


_LT = chr(60)
_GT = chr(62)
_DQ = chr(34)
_SQ = chr(39)
_P_TAG = 'parameter'

def _tag(n, a=""):
    return _LT + n + (" " + a if a else "") + _GT

def _tc(n):
    return _LT + "/" + n + _GT

_FC_S = '<function_calls>'
_FC_E = '</function_calls>'
_FR_S = '<function_results>'
_FR_E = '</function_results>'

class NousProtocol(ToolProtocol):
    """Nous Research XML format."""

    @property
    def id(self) -> str:
        return 'nous'

    def get_trigger_tags(self) -> List[str]:
        return [_FC_S]

    def render_prompt(
        self, tool_descs: str, lang: str,
        user_system_prompt: str = '',
        history_text: str = '',
        loop_warning: str = '',
        current_user_message: str = '',
    ) -> str:
        instruction = (
            '## Available Tools\n'
            'You can interact with the following tools:\n\n'
            + tool_descs + '\n\n'
            'When calling a tool, respond with:\n\n'
            + _FC_S + "\n"
            + '  ' + _tag('invoke', 'name=' + _DQ + 'exact_tool_name' + _DQ) + "\n"
            + '    ' + _tag(_P_TAG, 'name=' + _DQ + 'param' + _DQ) + '<![CDATA[value]]>' + _tc(_P_TAG) + "\n"
            + '  ' + _tc('invoke') + "\n"
            + _FC_E
        )
        sections = [instruction]
        if user_system_prompt and user_system_prompt.strip():
            sections.append('<user_system_prompt>\n' + user_system_prompt.strip() + '\n</user_system_prompt>')
        if history_text:
            clarify = _HISTORY_CLARIFY_ZH if lang == "zh" else _HISTORY_CLARIFY_EN
            sections.append('<conversation_history>\n' + clarify + '\n\n' + history_text + '\n</conversation_history>')
        if loop_warning:
            sections.append('<loop_warning>\n' + loop_warning + '\n</loop_warning>')
        if current_user_message:
            sections.append('<current_user_message>\n' + current_user_message + '\n</current_user_message>')
        return '\n\n'.join(sections)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        pos = buffer.find(_FC_S)
        if pos >= 0:
            return (True, pos)
        return (False, -1)

    def parse(self, text: str, tools: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, List[Dict[str, Any]]]:
        tool_calls: List[Dict[str, Any]] = []
        for block_m in _FC_BLOCK_RE.finditer(text):
            block_body = block_m.group(1)
            for inv_m in _INV_RE.finditer(block_body):
                func_name = inv_m.group(1).strip()
                params_text = inv_m.group(2)
                arguments = self._parse_params(params_text, func_name, tools)
                tool_calls.append({
                    'id': f'call_{len(tool_calls)}',
                    'type': 'function',
                    'function': {'name': func_name, 'arguments': arguments},
                })
        clean = text
        if tool_calls:
            clean = _FC_BLOCK_RE.sub('', text).strip()
        return clean, tool_calls

    def _parse_params(self, body: str, func_name: str, tools: Optional[List[Dict[str, Any]]] = None) -> str:
        result: Dict[str, Any] = {}
        schema_index = _build_param_schema_index(tools) if tools else None
        param_schemas: Dict[str, Dict[str, Any]] = {}
        if schema_index and func_name:
            param_schemas = schema_index.get(func_name) or {}
        for pm in _PARAM_RE.finditer(body):
            key = pm.group(1).strip()
            val = _CDATA_RE.sub(r'\1', pm.group(2)).strip()
            pschema = param_schemas.get(key) or {}
            if pschema:
                result[key] = _coerce_param_value(val, pschema)
            else:
                try:
                    result[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    result[key] = val
        return json.dumps(result, ensure_ascii=False) if result else '{}'

    def parse_fragment(self, fragment: str, tools: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content: str) -> str:
        cleaned = _FC_BLOCK_RE.sub('', content)
        return cleaned.strip()

    def format_assistant_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
        if not tool_calls:
            return ''
        invokes = []
        for tc_item in tool_calls:
            name = tc_item.get('function', {}).get('name', '')
            args = tc_item.get('function', {}).get('arguments', '{}')
            try:
                args_dict = json.loads(args) if isinstance(args, str) else args
            except (json.JSONDecodeError, ValueError):
                args_dict = {}
            params = ''
            for pname, pval in args_dict.items():
                text_val = pval if isinstance(pval, str) else json.dumps(pval, ensure_ascii=False)
                params += _tag(_P_TAG, 'name=' + _DQ + pname + _DQ) + '<![CDATA[' + text_val + ']]>' + _tc(_P_TAG)

            invokes.append(_tag('invoke', 'name=' + _DQ + name + _DQ) + params + _tc('invoke'))

        return _FC_S + ''.join(invokes) + _FC_E

    def format_tool_result(self, content: str, tool_name: str = '', is_error: bool = False, tool_call_id: str = '') -> str:
        return (
            _FR_S
            + _tag('function_result', 'name=' + _DQ + tool_name + _DQ + ' tool_call_id=' + _DQ + tool_call_id + _DQ)
            + '<![CDATA[' + content + ']]>'
            + _tc('function_result')
            + _FR_E
        )

    def supports_streaming(self) -> bool:
        return True
