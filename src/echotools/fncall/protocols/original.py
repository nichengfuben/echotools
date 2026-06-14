"""Original 协议（OpenAI 原生 codexResponses JSON 格式）。

该协议匹配平台原生的 codexResponses 格式：
  {"type": "function_call", "name": "...", "arguments": {...}}

支持多种嵌套结构：
  - 直接的 function_call 对象
  - 数组: [...]
  - 嵌套在 output: {"output": [...]}
  - 嵌套在 items: {"items": [...]}
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
from echotools.fncall.shared.coercion import (
    _build_param_schema_index,
    _coerce_param_value,
)


# ---------------------------------------------------------------------------
# JSON 块定位正则
# ---------------------------------------------------------------------------

# 匹配最外层 JSON 对象/数组（支持嵌套括号/括号对计数）
_JSON_BLOCK_RE = re.compile(r"[\[{]")


# ---------------------------------------------------------------------------
# Original 协议
# ---------------------------------------------------------------------------


class OriginalProtocol(ToolProtocol):
    """OpenAI 原生 codexResponses 协议适配器。

    通过检测 ``"type":"function_call"`` 或 ``"type": "function_call"`` 来
    识别协议起始位置，然后从 JSON 中提取工具调用。
    """

    @property
    def id(self) -> str:
        return "original"

    _TRIGGERS: Tuple[str, str] = ('"type":"function_call"', '"type": "function_call"')

    def get_trigger_tags(self) -> List[str]:
        return list(self._TRIGGERS)

    def render_prompt(
        self,
        tool_descs: str,
        lang: str,
        user_system_prompt: str = "",
        history_text: str = "",
        loop_warning: str = "",
        current_user_message: str = "",
    ) -> str:
        """该协议依赖平台原生工具调用，无需 prompt 注入。

        仅透传必要的上下文信息（如用户 system prompt、历史对话等）。
        ``tool_descs`` 和 ``lang`` 在此协议中不使用（平台原生处理）。
        ``loop_warning`` 是安全机制，始终注入。
        """
        parts: List[str] = []

        if user_system_prompt:
            parts.append(user_system_prompt)

        if history_text:
            clarify = _HISTORY_CLARIFY_ZH if lang == "zh" else _HISTORY_CLARIFY_EN
            parts.append(f"{clarify}\n\n{history_text}")

        if loop_warning:
            parts.append(f"<loop_warning>\n{loop_warning}\n</loop_warning>")

        if current_user_message:
            parts.append(current_user_message)

        return "\n\n".join(parts)

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        """检测 buffer 中是否出现 function_call 触发标记。"""
        for trigger in self._TRIGGERS:
            pos = buffer.find(trigger)
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
        cleaned = text

        schema_index = _build_param_schema_index(tools) if tools else None

        # 找到所有 JSON 块并尝试解析
        json_blocks = _find_json_blocks(text)
        removed_spans: List[Tuple[int, int]] = []

        for block_text, start, end in json_blocks:
            try:
                parsed = json.loads(block_text)
            except (json.JSONDecodeError, ValueError):
                continue

            items = _extract_response_items(parsed)
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "function_call":
                    continue

                name = item.get("name")
                if not name:
                    continue

                call_id = item.get("call_id") or item.get("id") or f"call_{len(tool_calls)}"
                args_raw = item.get("arguments", {})

                # Schema 感知的参数类型转换
                if schema_index and name in schema_index:
                    args_dict = args_raw if isinstance(args_raw, dict) else {}
                    args: Dict[str, Any] = {}
                    for k, v in args_dict.items():
                        pschema = schema_index[name].get(k, {})
                        v_str = (
                            v if isinstance(v, str)
                            else json.dumps(v, ensure_ascii=False)
                        )
                        args[k] = _coerce_param_value(v_str, pschema)
                    arguments = json.dumps(args, ensure_ascii=False)
                else:
                    arguments = (
                        json.dumps(args_raw, ensure_ascii=False)
                        if not isinstance(args_raw, str)
                        else args_raw
                    )

                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                })

            # 标记这个 JSON 块已被消耗
            if items:
                removed_spans.append((start, end))

        # 从 cleaned 中移除已消耗的 JSON 块
        if removed_spans:
            cleaned = _remove_spans(text, removed_spans)

        return (cleaned, tool_calls)

    def parse_fragment(
        self,
        fragment: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """将已知的完整 JSON 片段直接解析为 tool_calls 列表。"""
        _, tool_calls = self.parse(fragment, tools)
        return tool_calls

    def clean_tags(self, content: str) -> str:
        """从响应文本中移除所有 JSON function_call 块。"""
        blocks = _find_json_blocks(content)
        if not blocks:
            return content.strip()

        # 只移除包含 function_call 的块
        removed_spans: List[Tuple[int, int]] = []
        for block_text, start, end in blocks:
            if '"function_call"' in block_text:
                removed_spans.append((start, end))

        if removed_spans:
            content = _remove_spans(content, removed_spans)

        return content.strip()

    def format_assistant_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> str:
        """将 tool_call 对象列表渲染为 codexResponses JSON 格式。"""
        if not tool_calls:
            return ""

        items: List[Dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            call_id = tc.get("id")
            try:
                arguments = json.loads(fn.get("arguments", "{}"))
            except (json.JSONDecodeError, ValueError):
                arguments = fn.get("arguments", "{}")

            item: Dict[str, Any] = {
                "type": "function_call",
                "name": fn.get("name", ""),
                "arguments": arguments,
            }
            if call_id:
                item["call_id"] = call_id

            items.append(item)

        return json.dumps(items, ensure_ascii=False)

    def format_tool_result(
        self,
        content: str,
        tool_name: str = "",
        is_error: bool = False,
    ) -> str:
        """将工具执行结果渲染为 codexResponses 格式。"""
        return content

    def supports_streaming(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _extract_response_items(value: Any) -> List[Any]:
    """从各种 JSON 结构中提取响应项列表。

    支持以下格式：
      - 数组: 直接返回
      - {"type": "function_call"}: 包装为单元素列表
      - {"output": [...]}: 返回 output
      - {"items": [...]}: 返回 items
    """
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []

    # 直接 function_call 对象
    if value.get("type") == "function_call":
        return [value]

    # 嵌套在 output 中
    output = value.get("output")
    if isinstance(output, list):
        return output

    # 嵌套在 items 中
    items = value.get("items")
    if isinstance(items, list):
        return items

    return []


def _find_json_blocks(text: str) -> List[Tuple[str, int, int]]:
    """在文本中查找完整的 JSON 对象/数组块。

    返回 [(json_string, start_pos, end_pos), ...]
    使用括号计数来定位最外层匹配的 JSON。
    """
    blocks: List[Tuple[str, int, int]] = []
    length = len(text)
    i = 0

    while i < length:
        ch = text[i]
        if ch not in ("{", "["):
            i += 1
            continue

        # 定位 JSON 块结束位置
        end = _find_json_end(text, i)
        if end < 0:
            i += 1
            continue

        block_text = text[i : end + 1]
        try:
            json.loads(block_text)
            blocks.append((block_text, i, end + 1))
        except (json.JSONDecodeError, ValueError):
            i += 1
            continue

        # 跳过已消耗的字符
        i = end + 1

    return blocks


def _find_json_end(text: str, start: int) -> int:
    """从 start 位置开始，找到匹配的 JSON 结束位置。

    使用计数器跟踪嵌套的 {} 和 []。
    返回结束字符的索引，未找到返回 -1。
    """
    length = len(text)
    open_char = text[start]
    if open_char == "{":
        close_char = "}"
    elif open_char == "[":
        close_char = "]"
    else:
        return -1

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, length):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\" and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i

    return -1


def _remove_spans(text: str, spans: List[Tuple[int, int]]) -> str:
    """从文本中移除指定区间的内容，并清理多余空白。"""
    if not spans:
        return text

    # 按起始位置排序
    spans = sorted(spans, key=lambda s: s[0])

    parts: List[str] = []
    prev_end = 0

    for start, end in spans:
        # 确保不重叠
        safe_start = max(start, prev_end)
        if safe_start > prev_end:
            parts.append(text[prev_end:safe_start])
        prev_end = max(prev_end, end)

    # 尾部
    if prev_end < len(text):
        parts.append(text[prev_end:])

    return "".join(parts).strip()
