from __future__ import annotations

"""LLM token usage 规范化。"""

from typing import Any, Dict

__all__ = ["normalize_usage", "fallback_usage"]


def fallback_usage(prompt_len: int, resp_text: str) -> Dict[str, int]:
    """估算 token 用量（无精确数据时的回退）。

    按字符数 / 3 粗略估算。

    Args:
        prompt_len: 提示文本字符数。
        resp_text: 响应文本。

    Returns:
        用量字典。
    """
    pt = max(prompt_len // 3, 1)
    ct = max(len(resp_text) // 3, 0)
    return {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct}


def normalize_usage(
    raw: Any,
    prompt_len: int,
    resp_text: str,
) -> Dict[str, int]:
    """规范化 usage 字典。

    兼容 OpenAI (prompt_tokens/completion_tokens) 和
    Anthropic (input_tokens/output_tokens) 格式。

    Args:
        raw: 原始 usage 数据（dict 或 None）。
        prompt_len: 提示文本字符数。
        resp_text: 响应文本。

    Returns:
        规范化后的用量字典。
    """
    if not isinstance(raw, dict):
        return fallback_usage(prompt_len, resp_text)
    try:
        pt = int(raw.get("prompt_tokens", raw.get("input_tokens", 0)))
        ct = int(raw.get("completion_tokens", raw.get("output_tokens", 0)))
        if pt <= 0 and ct <= 0:
            return fallback_usage(prompt_len, resp_text)
        if pt <= 0:
            pt = prompt_len // 3
        return {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": pt + ct,
        }
    except (TypeError, ValueError):
        return fallback_usage(prompt_len, resp_text)
