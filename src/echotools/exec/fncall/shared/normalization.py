"""内容规范化和工具描述格式化。

从 src/core/tools.py 迁移（原 lines 759-843）。
"""

from __future__ import annotations

import ast
import json
from typing import Any, Dict, List, Optional

from echotools.exec.fncall.shared.coercion import _build_param_schema_index
from echotools.exec.fncall.shared.schema_render import _render_schema_prop, _tag, _ctag, _DQ
from echotools.base.logger.manager import get_logger

logger = get_logger(__name__)


def normalize_content(content: Any) -> str:
    """将消息 content 字段规范化为纯字符串。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _normalize_list_content(content)
    if isinstance(content, dict):
        return _normalize_dict_content(content)
    return str(content)


def _normalize_list_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        if item.get("type") == "text" or "text" in item:
            text_val = item.get("text", "")
            return str(text_val) if text_val is not None else ""
        return json.dumps(item, ensure_ascii=False)
    return str(item)


def _normalize_list_content(content: list) -> str:
    parts = [_normalize_list_item(item) for item in content]
    return chr(10).join(p for p in parts if p)


def _normalize_dict_content(content: dict) -> str:
    if "text" in content:
        val = content["text"]
        return str(val) if val is not None else ""
    return json.dumps(content, ensure_ascii=False)


def format_tool_descs(tools):
    """将 OpenAI 格式工具定义列表格式化为 XML 描述字符串。"""
    if not tools:
        return ""

    parts = []
    for tool in tools:
        fn = tool.get("function", tool)
        name = fn.get("name") or "unknown"
        desc = fn.get("description") or ""
        params = fn.get("parameters") or {}
        props = params.get("properties") or {}
        required = params.get("required") or []

        lines = [_tag("tool", 'name=' + _DQ + name + _DQ)]
        if desc:
            lines.append(_tag("description") + desc + _ctag("description"))
        lines.append(_tag("parameters"))

        for pn, pi in props.items():
            if not isinstance(pi, dict):
                continue
            lines.extend(_render_schema_prop(pn, pi, required, depth=0, max_depth=4))

        lines.append(_ctag("parameters"))

        examples = fn.get("input_examples")
        if isinstance(examples, list) and examples:
            lines.append(_tag("input_examples"))
            for ex in examples:
                lines.append(_tag("example") + json.dumps(ex, ensure_ascii=False) + _ctag("example"))
            lines.append(_ctag("input_examples"))

        lines.append(_ctag("tool"))
        parts.append(chr(10).join(lines))

    return (chr(10) + chr(10)).join(parts)


def _try_parse_relaxed_literal(text: str) -> Optional[Any]:
    """仅对 array/object 形态尝试 JSON 或 Python literal 解析。"""
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{" or stripped[-1] not in "]}":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(stripped)
    except (ValueError, SyntaxError):
        return None


def _normalize_value(value: Any, schema: Optional[Dict[str, Any]] = None) -> Any:
    if isinstance(value, str):
        parsed = _try_parse_relaxed_literal(value)
        if parsed is not None:
            value = parsed
    if isinstance(value, list):
        item_schema = (schema or {}).get("items") if schema else None
        if isinstance(item_schema, dict):
            return [_normalize_value(item, item_schema) for item in value]
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        props = (schema or {}).get("properties") or {}
        return {
            key: _normalize_value(
                val,
                props.get(key) if isinstance(props.get(key), dict) else None,
            )
            for key, val in value.items()
        }
    return value


def normalize_tool_call(
    tc: Dict[str, Any],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """将 tool call arguments 中的 Python 字面量字符串还原为合法 JSON 结构。"""
    func = tc.get("function") or {}
    name = str(func.get("name") or "")
    raw_args = func.get("arguments", "{}")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("normalize_tool_call: invalid arguments JSON for %s", name)
        return tc

    schema_index = _build_param_schema_index(tools) if tools else {}
    param_schemas = schema_index.get(name, {})

    if isinstance(args, dict):
        args = {
            key: _normalize_value(
                val,
                param_schemas.get(key) if param_schemas else None,
            )
            for key, val in args.items()
        }
    else:
        args = _normalize_value(args)

    normalized = dict(tc)
    normalized["function"] = dict(func)
    normalized["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
    return normalized


def normalize_tool_calls(
    tool_calls: Optional[List[Dict[str, Any]]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """批量规范化 OpenAI 格式 tool_calls。"""
    if not tool_calls:
        return []
    return [normalize_tool_call(tc, tools) for tc in tool_calls]
