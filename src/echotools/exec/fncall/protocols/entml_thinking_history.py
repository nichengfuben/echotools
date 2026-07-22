from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

REASONING_KEYS = ("reasoning", "reasoning_content", "reasoning_details")
HISTORY_FLAG_KEYS = (
    "include_thinking_in_history",
    "pass_thinking",
    "include_thinking",
    "interleaved_history",
)
_THINKING_BLOCK_TYPES = frozenset({"thinking", "reasoning", "redacted_thinking"})


def parse_interleaved_history(
    body: Mapping[str, Any],
    extra: Optional[Mapping[str, Any]] = None,
    thinking: Any = None,
) -> bool:
    """解析是否将历史 assistant 思考链传给模型（Entropy interleaved_history）。"""
    extra = extra or {}
    if thinking is None:
        thinking = body.get("thinking")
    for key in ("interleaved_history", "include_in_history"):
        if key in body:
            return bool(body[key])
        if key in extra:
            return bool(extra[key])
    if isinstance(thinking, dict):
        for key in ("interleaved_history", "include_in_history"):
            if key in thinking:
                return bool(thinking[key])
    return False


def _thinking_from_content_block(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    btype = str(block.get("type", "")).strip().lower()
    if btype in ("thinking", "redacted_thinking"):
        val = block.get("thinking") or block.get("data")
        return str(val).strip() if val else ""
    if btype == "reasoning":
        val = block.get("text") or block.get("reasoning")
        return str(val).strip() if val else ""
    return ""


def extract_reasoning_text(msg: Mapping[str, Any]) -> str:
    """从 assistant 消息字段或 Entropy/Anthropic 内容块提取思考文本。"""
    for key in ("reasoning", "reasoning_content"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    details = msg.get("reasoning_details")
    if isinstance(details, list):
        parts: List[str] = []
        for item in details:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if text:
                parts.append(str(text))
        if parts:
            return "".join(parts)

    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            text = _thinking_from_content_block(block)
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
    return ""


def _strip_thinking_blocks(content: List[Any]) -> List[Any]:
    kept: List[Any] = []
    for block in content:
        if isinstance(block, dict) and str(block.get("type", "")).lower() in _THINKING_BLOCK_TYPES:
            continue
        kept.append(block)
    return kept


def _collapse_text_content(blocks: List[Any]) -> Any:
    if len(blocks) == 1:
        only = blocks[0]
        if isinstance(only, dict) and only.get("type") == "text":
            return only.get("text", "")
    return blocks


def _strip_reasoning_from_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(msg)
    for key in REASONING_KEYS:
        out.pop(key, None)
    content = out.get("content")
    if isinstance(content, list):
        stripped = _strip_thinking_blocks(content)
        out["content"] = _collapse_text_content(stripped) if stripped else ""
    return out


def _normalize_message_with_reasoning(msg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(msg)
    if out.get("role") != "assistant":
        for key in REASONING_KEYS:
            out.pop(key, None)
        return out

    text = extract_reasoning_text(out)
    if text:
        out["reasoning"] = text
        out.setdefault("reasoning_content", text)
    return out


def apply_thinking_history_policy(
    messages: List[Dict[str, Any]],
    include: bool,
) -> List[Dict[str, Any]]:
    """按 interleaved_history 保留或剥离历史思考链。

    include=True: 保留 reasoning 字段与 content 中的 thinking 块。
    include=False: 仅保留可见回复，剥离思考链。
    """
    if include:
        return [_normalize_message_with_reasoning(dict(m)) for m in messages]
    return [_strip_reasoning_from_message(dict(m)) for m in messages]
