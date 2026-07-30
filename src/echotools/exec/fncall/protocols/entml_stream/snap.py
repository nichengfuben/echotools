from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from echotools.exec.fncall.protocols.entml_stream.body import (
    _INVOKE_CLOSE,
    _PARAMETERS_CLOSE,
    _PARAMETERS_OPEN,
    _effective_param_type,
    _final_invoke_arguments_json,
    _parameter_json_fragment,
    _parse_bare_invoke_entries,
    _parse_direct_child_entries,
    _parse_parameter_entries,
)

def _parameters_block_snapshot(
    inner: str,
    *,
    tool_name: str,
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]],
) -> Optional[str]:
    """处理 ``<entml:parameters>`` 整包参数（流式前缀或完整 JSON）。"""
    open_pos = inner.find(_PARAMETERS_OPEN)
    if open_pos < 0:
        return None
    content_start = open_pos + len(_PARAMETERS_OPEN)
    close_pos = inner.find(_PARAMETERS_CLOSE, content_start)
    if close_pos >= 0:
        closed_body = inner[: close_pos + len(_PARAMETERS_CLOSE)]
        from echotools.exec.fncall.protocols.entml_invoke import parse_invoke_args

        args = parse_invoke_args(closed_body, tool_name, schema_index)
        return json.dumps(args, ensure_ascii=False)
    return ""


def build_streaming_json_snapshot(
    body: str,
    *,
    tool_name: str = "",
    schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    force_close: bool = False,
) -> str:
    """构造当前应已发出的 partial_json 累积串（可未完成）。

    invoke 闭合（或 force_close）时直接走 ``parse_invoke_args``，与批量解析一致。
    未完成时仅输出合法 JSON 前缀，且不在 ``</entml:invoke>`` 前闭合最外层 ``}``。
    """
    invoke_closed = _INVOKE_CLOSE in body
    inner = body[: body.index(_INVOKE_CLOSE)] if invoke_closed else body

    if invoke_closed or force_close:
        return _final_invoke_arguments_json(
            body,
            tool_name=tool_name,
            schema_index=schema_index,
            force_close=force_close,
        )

    params_snap = _parameters_block_snapshot(
        inner, tool_name=tool_name, schema_index=schema_index
    )
    if params_snap is not None:
        return params_snap

    entries = _parse_parameter_entries(inner)
    seen_keys = {key for key, *_rest in entries}
    for bare in _parse_bare_invoke_entries(inner):
        if bare[0] not in seen_keys:
            entries.append(bare)
            seen_keys.add(bare[0])
    for direct in _parse_direct_child_entries(inner):
        if direct[0] not in seen_keys:
            entries.append(direct)
            seen_keys.add(direct[0])
    if not entries:
        return ""

    func_schema = (schema_index or {}).get(tool_name) or {}
    parts: List[str] = ["{"]
    for idx, (key, value, is_complete, type_hint) in enumerate(entries):
        if idx > 0:
            parts.append(", ")
        parts.append(json.dumps(key, ensure_ascii=False))
        parts.append(": ")
        pschema = func_schema.get(key) or {}
        param_type = _effective_param_type(value, pschema, type_hint)
        fragment = _parameter_json_fragment(
            value, is_complete, param_type, pschema, type_hint
        )
        if fragment is None:
            if idx == 0:
                return ""
            return "".join(parts)
        parts.append(fragment)
        if not is_complete:
            return "".join(parts)

    return "".join(parts)


def _parse_partial_parameter_body(body: str) -> Dict[str, Any]:
    obj: Dict[str, Any] = {}
    for key, value, is_complete, _type_hint in _parse_parameter_entries(
        body[: body.index(_INVOKE_CLOSE)] if _INVOKE_CLOSE in body else body
    ):
        if is_complete or value:
            obj[key] = value
    return obj


def encode_streaming_invoke_json(body: str) -> str:
    obj = _parse_partial_parameter_body(body)
    if not obj:
        return ""
    return json.dumps(obj, ensure_ascii=False)


class EntmlInvokeJsonStreamEncoder:
    """invoke 开标签之后，将 growing body 编码为可拼接的 partial_json 增量。"""

    def __init__(
        self,
        *,
        tool_name: str = "",
        schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        self._emitted = ""
        self._tool_name = tool_name
        self._schema_index = schema_index

    def set_tool_context(
        self,
        tool_name: str,
        schema_index: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
    ) -> None:
        if tool_name != self._tool_name:
            self._emitted = ""
        self._tool_name = tool_name
        self._schema_index = schema_index

    def poll(self, body: str, *, force_close: bool = False) -> str:
        snapshot = build_streaming_json_snapshot(
            body,
            tool_name=self._tool_name,
            schema_index=self._schema_index,
            force_close=force_close,
        )
        if not snapshot:
            return ""
        if not snapshot.startswith(self._emitted):
            common = 0
            for a, b in zip(self._emitted, snapshot):
                if a != b:
                    break
                common += 1
            if common < len(self._emitted):
                self._emitted = snapshot
                return ""
            delta = snapshot[common:]
            self._emitted = snapshot
            return delta
        delta = snapshot[len(self._emitted) :]
        self._emitted = snapshot
        return delta

    def reset(self) -> None:
        self._emitted = ""
