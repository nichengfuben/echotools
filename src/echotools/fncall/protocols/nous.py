"""Nous Research / Hermes style tool invocation protocol.

Format: function=name with JSON args, tools block, tool_response.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from echotools.protocol.base import ToolProtocol
from echotools.fncall.prompt.templates import (
    _HISTORY_CLARIFY_EN,
    _HISTORY_CLARIFY_ZH,
)

# Tag constants
_LT = chr(60)
_GT = chr(62)
_FN_TAG = _LT + 'function='
_FN_END = _LT + '/function' + _GT
_TR_TAG = _LT + 'tool_response' + _GT
_TR_END = _LT + '/tool_response' + _GT
_TOOLS_S = _LT + 'tools' + _GT
_TOOLS_E = _LT + '/tools' + _GT

# Regex
_FN_CALL_RE = re.compile(r'<function=([^>]*)>([\s\S]*?)</function>', re.DOTALL)
_FN_CLEAN_RE = re.compile(r'<function=[^>]*>[\s\S]*?</function>', re.DOTALL)
_TR_BLOCK_RE = re.compile(r'<tool_response>[\s\S]*?</tool_response>', re.DOTALL)


def _format_tool_descs_nous(tools):
    """Format tool definitions in Nous XML style."""
    if not tools:
        return ""
    parts = []
    for tool in tools:
        fn = tool.get('function', tool)
        name = fn.get('name', 'unknown')
        desc = fn.get('description', '')
        params = fn.get('parameters', {})
        pj = json.dumps(params, ensure_ascii=False)
        parts.append(
            _LT + 'function' + _GT + '\n'
            + _LT + 'name' + _GT + name + _LT + '/name' + _GT + '\n'
            + _LT + 'description' + _GT + desc + _LT + '/description' + _GT + '\n'
            + _LT + 'parameters' + _GT + pj + _LT + '/parameters' + _GT + '\n'
            + _LT + '/function' + _GT
        )
    return '\n\n'.join(parts)


class NousProtocol(ToolProtocol):
    """Nous Research / Hermes function calling format."""

    @property
    def id(self) -> str:
        return 'nous'

    def get_trigger_tags(self) -> List[str]:
        return [_FN_TAG]

    def format_tool_descs(self, tools):
        return _format_tool_descs_nous(tools)

    def render_prompt(self, tool_descs, lang, user_system_prompt='', history_text='', loop_warning='', current_user_message=''):
        ex = _FN_TAG + 'function_name' + _GT + '{"param": "value"}' + _FN_END
        if lang == 'zh':
            inst = (
                '你是一个乐于助人的 AI 助手。\n\n'
                + '# 工具\n\n'
                + '你可以使用以下函数：\n\n'
                + _TOOLS_S + '\n' + tool_descs + '\n' + _TOOLS_E + '\n\n'
                + '调用格式：\n\n' + ex
            )
        else:
            inst = (
                'You are a helpful AI assistant with tool access.\n\n'
                + '# Tools\n\n'
                + 'Available functions:\n\n'
                + _TOOLS_S + '\n' + tool_descs + '\n' + _TOOLS_E + '\n\n'
                + 'Call format:\n\n' + ex
            )
        sections = [inst]
        if user_system_prompt and user_system_prompt.strip():
            sections.append(user_system_prompt.strip())
        if history_text:
            clarify = _HISTORY_CLARIFY_ZH if lang == 'zh' else _HISTORY_CLARIFY_EN
            sections.append(clarify + '\n\n' + history_text)
        if loop_warning:
            sections.append(loop_warning)
        if current_user_message:
            sections.append(current_user_message)
        return '\n\n'.join(sections)

    def detect_start(self, buffer):
        pos = buffer.find(_FN_TAG)
        if pos >= 0:
            return (True, pos)
        return (False, -1)

    def parse(self, text, tools=None):
        tool_calls = []
        for m in _FN_CALL_RE.finditer(text):
            func_name = m.group(1).strip()
            args_text = m.group(2).strip()
            try:
                args_dict = json.loads(args_text) if args_text else {}
            except (json.JSONDecodeError, ValueError):
                args_dict = {}
            tool_calls.append({
                'id': 'call_{}'.format(len(tool_calls)),
                'type': 'function',
                'function': {
                    'name': func_name,
                    'arguments': json.dumps(args_dict, ensure_ascii=False),
                },
            })
        clean = text
        if tool_calls:
            clean = _FN_CLEAN_RE.sub('', text).strip()
        return clean, tool_calls

    def parse_fragment(self, fragment, tools=None):
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content):
        cleaned = _FN_CLEAN_RE.sub('', content)
        cleaned = _TR_BLOCK_RE.sub('', cleaned)
        return cleaned.strip()

    def format_assistant_tool_calls(self, tool_calls):
        if not tool_calls:
            return ''
        parts = []
        for tc in tool_calls:
            name = tc.get('function', {}).get('name', '')
            args = tc.get('function', {}).get('arguments', '{}')
            parts.append(_FN_TAG + name + _GT + args + _FN_END)
        return '\n'.join(parts)

    def format_tool_result(self, content, tool_name='', is_error=False, tool_call_id=''):
        return _TR_TAG + '\n' + content + '\n' + _TR_END

    def supports_streaming(self):
        return True
