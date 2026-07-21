from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from echotools.exec.fncall.shared.coercion import _coerce_param_value
from echotools.exec.fncall.shared.normalization import normalize_tool_calls


def parse_param_xml(
    params_xml: str,
    param_schemas: Dict[str, Dict[str, Any]],
    param_re: Any,
    value_fn: Any = None,
) -> Dict[str, Any]:
    normalize = value_fn or (lambda v: v)
    arguments: Dict[str, Any] = {}
    for pm in param_re.finditer(params_xml):
        key = pm.group(1).strip()
        val = normalize(pm.group(2).strip())
        pschema = param_schemas.get(key) or {}
        if pschema:
            arguments[key] = _coerce_param_value(val, pschema)
            continue
        try:
            arguments[key] = json.loads(val)
        except (json.JSONDecodeError, ValueError):
            arguments[key] = val
    return arguments


def make_tool_call(func_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"call_{uuid.uuid4().hex[:24]}",
        "type": "function",
        "function": {
            "name": func_name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }
