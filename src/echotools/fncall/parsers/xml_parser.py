"""XML 协议解析器。

从 src/core/tools.py 迁移。仅用于 xml 协议。
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from echotools.fncall.shared.coercion import _build_param_schema_index, _coerce_param_value
from echotools.fncall.shared.xml_helpers import (
    _CDATA_RE,
    _PROVIDER_BLOCK_RE,
    _PROVIDER_INVOKE_RE,
    _PROVIDER_PARAM_RE,
    extract_cdata,
)
from echotools.logger.manager import get_logger

logger = get_logger(__name__)

# 正则常量
_FNCALL_BLOCK_RE = re.compile(
    r"<function_calls>(.*?)</function_calls>",
    re.DOTALL,
)
_INVOKE_RE = re.compile(
    r'<invoke\s+name="([^"]+)">(.*?)</invoke>',
    re.DOTALL,
)
_PARAM_NAME_RE = re.compile(
    r'<parameter\s+name="([^"]+)">(.*?)</parameter>',
    re.DOTALL,
)

_FE = "</" + "function>"
_FE_ESC = re.escape(_FE)
_FUNC_RE = re.compile(r"<function=([^>]+)>(.*?)" + _FE_ESC, re.DOTALL)

_PARAM_RE = re.compile(
    r"<([a-zA-Z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)>\s*\n?(.*?)\n?\s*</\1>",
    re.DOTALL,
)
_TOOL_CALL_LINE_RE = re.compile(
    r"^Tool call \(([^)]+)\)\s*:\s*(\w[\w.]*)\((\{.*?\})\)\s*$",
    re.MULTILINE | re.DOTALL,
)
_TOOL_CALL_ID_RE = re.compile(
    r"Tool call \(([^)]+)\)\s*:",
)
_TOOL_RESULT_LINE_RE = re.compile(
    r"^Tool result \(([^)]+)\)\s*:\s*",
)

def _parse_invoke_body(
    body: str,
    func_name: str = "",
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> str:
    """将 <invoke> 标签体中的 <parameter> 列表解析为 JSON arguments 字符串。

    新增 schema_index 参数：若提供，对每个参数值调用 _coerce_param_value
    进行 schema 感知类型转换。

    Args:
        body: <invoke> 内部的原始字符串。
        func_name: 函数名，用于在 schema_index 中查找参数 schema。
        schema_index: _build_param_schema_index() 返回的索引，可为 None。

    Returns:
        JSON 格式的 arguments 字符串，无参数时返回 "{}"。
    """
    matches = list(_PARAM_NAME_RE.finditer(body))
    if not matches:
        return "{}"

    # 获取当前函数的参数 schema 映射
    param_schemas: Dict[str, Dict[str, Any]] = {}
    if schema_index and func_name:
        param_schemas = schema_index.get(func_name) or {}

    result: Dict[str, Any] = {}
    for m in matches:
        pname = m.group(1)
        pval = m.group(2).strip("\n")
        pschema = param_schemas.get(pname) or {}
        if pschema:
            result[pname] = _coerce_param_value(pval, pschema)
        else:
            # 无 schema → 原有启发式行为
            try:
                result[pname] = json.loads(pval)
            except json.JSONDecodeError:
                result[pname] = pval

    return json.dumps(result, ensure_ascii=False)

def _get_known_params(
    func_name: str,
    tools: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """返回指定函数的已知参数名列表。"""
    if not tools:
        return []
    for t in tools:
        fn = t.get("function", t)
        if fn.get("name") == func_name:
            return list((fn.get("parameters") or {}).get("properties", {}).keys())
    return []

def _parse_func_body(
    body: str,
    func_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> str:
    """将旧格式 <function=name> 标签体解析为 JSON arguments 字符串。"""
    known = _get_known_params(func_name, tools)
    param_schemas: Dict[str, Dict[str, Any]] = {}
    if schema_index and func_name:
        param_schemas = schema_index.get(func_name) or {}

    matches = list(_PARAM_RE.finditer(body))

    if matches:
        result: Dict[str, Any] = {}
        for m_obj in matches:
            pname = m_obj.group(1).strip()
            pval = m_obj.group(2).strip()
            if known and pname not in known:
                continue
            pschema = param_schemas.get(pname) or {}
            if pschema:
                result[pname] = _coerce_param_value(pval, pschema)
            else:
                try:
                    result[pname] = json.loads(pval)
                except json.JSONDecodeError:
                    result[pname] = pval
        if result:
            return json.dumps(result, ensure_ascii=False)

    stripped = body.strip()
    if stripped:
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            logger.debug(
                "_parse_func_body: 参数体非 JSON，回退为空对象: func=%s", func_name
            )

    return "{}"

def parse_fncall(
    text: str,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """从文本中提取函数调用，返回 (清理后文本, tool_calls 列表)。

    解析优先级（互斥）：
    1. 新格式：<function_calls><invoke name="...">...</invoke></function_calls>
    2. 旧格式：<function=name>...</function>

    类型转换：
    若提供 tools，对每个参数值根据对应的 JSON Schema 做精确类型转换。
    """
    calls: List[Dict[str, Any]] = []

    # 预构建 schema 索引（O(n) 一次构建，避免每个参数重复线性搜索）
    schema_index = _build_param_schema_index(tools) if tools else None

    for block_m in _FNCALL_BLOCK_RE.finditer(text):
        block_body = block_m.group(1)
        for inv_m in _INVOKE_RE.finditer(block_body):
            func_name = inv_m.group(1).strip()
            body = inv_m.group(2)
            arguments = _parse_invoke_body(body, func_name, schema_index)
            calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                }
            )

    if not calls:
        for m_obj in _FUNC_RE.finditer(text):
            func_name = m_obj.group(1).strip()
            body = m_obj.group(2)
            arguments = _parse_func_body(body, func_name, tools, schema_index)
            calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {"name": func_name, "arguments": arguments},
                }
            )

    clean = text
    if calls:
        clean = _FNCALL_BLOCK_RE.sub("", clean)
        clean = _FUNC_RE.sub("", clean)
        clean = clean.strip()

    return clean, calls

def parse_fncall_xml(
    xml: str,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """将 function_calls XML 片段直接解析为 OpenAI tool_calls 格式列表。

    新增 tools 参数：若提供，对参数值做 schema 感知类型转换。

    Args:
        xml: 包含 <invoke> 块的 XML 字符串。
        tools: 工具定义列表，用于类型转换（可为 None）。

    Returns:
        tool_calls 列表；解析失败时返回 []。
    """
    tool_calls: List[Dict[str, Any]] = []
    schema_index = _build_param_schema_index(tools) if tools else None

    try:
        for match in _INVOKE_RE.finditer(xml):
            func_name = match.group(1).strip()
            params_xml = match.group(2)
            param_schemas: Dict[str, Dict[str, Any]] = {}
            if schema_index:
                param_schemas = schema_index.get(func_name) or {}

            arguments: Dict[str, Any] = {}
            for pm in _PARAM_NAME_RE.finditer(params_xml):
                key = pm.group(1).strip()
                val = pm.group(2).strip()
                pschema = param_schemas.get(key) or {}
                if pschema:
                    arguments[key] = _coerce_param_value(val, pschema)
                else:
                    try:
                        arguments[key] = json.loads(val)
                    except (json.JSONDecodeError, ValueError):
                        arguments[key] = val

            tool_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                }
            )
    except Exception as exc:
        logger.warning("parse_fncall_xml 解析失败: %s", exc)

    return tool_calls


def parse_fncall_managed_xml(
    xml: str,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """解析 <|PROVIDER|tool_calls> 格式的 XML。

    支持 CDATA 包裹的参数值。

    Args:
        xml: 包含 <|PROVIDER|invoke> 块的 XML 字符串。
        tools: 工具定义列表，用于类型转换（可为 None）。

    Returns:
        tool_calls 列表；解析失败时返回 []。
    """
    tool_calls: List[Dict[str, Any]] = []
    schema_index = _build_param_schema_index(tools) if tools else None

    try:
        for block_m in _PROVIDER_BLOCK_RE.finditer(xml):
            block_body = block_m.group(1)
            for inv_m in _PROVIDER_INVOKE_RE.finditer(block_body):
                func_name = inv_m.group(1).strip()
                params_xml = inv_m.group(2)
                param_schemas: Dict[str, Dict[str, Any]] = {}
                if schema_index:
                    param_schemas = schema_index.get(func_name) or {}

                arguments: Dict[str, Any] = {}
                for pm in _PROVIDER_PARAM_RE.finditer(params_xml):
                    key = pm.group(1).strip()
                    val = extract_cdata(pm.group(2))
                    pschema = param_schemas.get(key) or {}
                    if pschema:
                        arguments[key] = _coerce_param_value(val, pschema)
                    else:
                        try:
                            arguments[key] = json.loads(val)
                        except (json.JSONDecodeError, ValueError):
                            arguments[key] = val

                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": json.dumps(arguments, ensure_ascii=False),
                        },
                    }
                )
    except Exception as exc:
        logger.warning("parse_fncall_managed_xml 解析失败: %s", exc)

    return tool_calls
