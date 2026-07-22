from __future__ import annotations

import json
from typing import Any, Dict, List

__all__ = ["format_entml_tool_descs"]


def format_entml_tool_descs(tools: List[Dict[str, Any]]) -> str:
    """将工具列表格式化为 **name** + JSON Schema 代码块（对齐 entml/antml 示范）。"""
    if not tools:
        return ""

    blocks: List[str] = []
    for tool in tools:
        fn = tool.get("function", tool)
        name = str(fn.get("name") or "unknown")
        payload = {
            "description": fn.get("description") or "",
            "name": name,
            "parameters": fn.get("parameters")
            or {"type": "object", "properties": {}},
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        blocks.append(f"**{name}**\n\n```json\n{body}\n```")
    return "\n\n".join(blocks)
