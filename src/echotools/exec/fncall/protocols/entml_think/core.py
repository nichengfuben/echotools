from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from echotools.exec.fncall.prompt.behavior_blocks import format_thinking_behavior

_CANONICAL_LEVELS = frozenset({"none", "low", "medium", "high", "xhigh", "max", "auto"})
_CANONICAL_INJECTION_MODES = frozenset({"off", "on", "auto"})

_LEVEL_ALIASES: Dict[str, str] = {
    "none": "none",
    "off": "none",
    "disabled": "none",
    "disable": "none",
    "false": "none",
    "no": "none",
    "never": "none",
    "low": "low",
    "medium": "medium",
    "med": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "extra_high": "xhigh",
    "extrahigh": "xhigh",
    "max": "max",
    "maximum": "max",
    "auto": "auto",
    "automatic": "auto",
    "adaptive": "auto",
    "interleaved": "auto",
}

_INJECTION_MODE_ALIASES: Dict[str, str] = {
    "off": "off",
    "disabled": "off",
    "disable": "off",
    "false": "off",
    "none": "off",
    "no": "off",
    "never": "off",
    "on": "on",
    "enabled": "on",
    "enable": "on",
    "true": "on",
    "force": "on",
    "forced": "on",
    "required": "on",
    "must": "on",
    "static": "on",
    "thinking": "on",
    "auto": "auto",
    "automatic": "auto",
    "adaptive": "auto",
    "interleaved": "auto",
}

_DEFAULT_MAX_BY_LEVEL: Dict[str, int] = {
    "low": 12800,
    "medium": 25600,
    "high": 64000,
    "xhigh": 102400,
    "max": 134736,
}

_LEGACY_ON_DEFAULT_MAX = _DEFAULT_MAX_BY_LEVEL["medium"]


def normalize_thinking_level(level: Any) -> Optional[str]:
    """将 echotools 思考挡位归一化为 none | low | medium | high | xhigh | max | auto。"""
    if level is None:
        return None
    key = str(level).strip().lower()
    if not key:
        return None
    if key in _CANONICAL_LEVELS:
        return key
    return _LEVEL_ALIASES.get(key)


def normalize_thinking_mode(mode: Any) -> Optional[str]:
    """将注入侧思考模式归一化为 off | on | auto（兼容旧 thinking_mode 字段）。"""
    if mode is None:
        return None
    key = str(mode).strip().lower()
    if not key:
        return None
    if key in _CANONICAL_INJECTION_MODES:
        return key
    return _INJECTION_MODE_ALIASES.get(key)


def default_max_thinking_length_for_level(level: str) -> Optional[int]:
    """按挡位返回默认 max_thinking_length；none / auto 无默认值。"""
    return _DEFAULT_MAX_BY_LEVEL.get(level)


def parse_max_thinking_length(value: Any) -> Optional[int]:
    """仅当显式传入正整数时返回长度；否则为 None。"""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def resolve_thinking_injection(
    protocol_options: Optional[Dict[str, Any]] = None,
) -> Optional[Tuple[str, Optional[int]]]:
    """解析注入用 thinking_mode 与 max_thinking_length。

    - thinking_level 为 low|medium|high|xhigh|max 时，thinking_mode 直接传该挡位名。
    - 仅 thinking_mode=on（无 level）时用 ``on``，并按 medium 默认长度。
    - auto 传 ``auto``，无默认 max_thinking_length。
    - none / off 返回 None，不注入任何思考相关内容。
    """
    opts = protocol_options or {}

    level = normalize_thinking_level(opts.get("thinking_level"))
    if level is not None:
        if level == "none":
            return None
        if level == "auto":
            injection_mode = "auto"
            default_max = None
        else:
            injection_mode = level
            default_max = default_max_thinking_length_for_level(level)
    else:
        mode = normalize_thinking_mode(opts.get("thinking_mode"))
        if mode is None or mode == "off":
            return None
        injection_mode = mode
        default_max = _LEGACY_ON_DEFAULT_MAX if mode == "on" else None

    explicit_max = parse_max_thinking_length(opts.get("max_thinking_length"))
    max_length = explicit_max if explicit_max is not None else default_max
    return injection_mode, max_length


def is_thinking_enabled(protocol_options: Optional[Dict[str, Any]] = None) -> bool:
    """是否开启思考模式（容错与 plain ``<thinking>`` 仅在此为 True 时生效）。

    未传 ``protocol_options`` 时视为已开启（兼容旧调用）；显式 ``off`` / ``none`` 时关闭。
    """
    if protocol_options is None:
        return True
    return resolve_thinking_injection(protocol_options) is not None


def build_entml_thinking_behavior_section(
    protocol_options: Optional[Dict[str, Any]] = None,
    *,
    history_text: str = "",
    has_tools: bool = True,
) -> str:
    """注入 ``<thinking_behavior>``（位于 history 之前）。"""
    from echotools.exec.fncall.protocols.entml_think.hist import (
        history_text_contains_entml_thinking,
    )

    resolved = resolve_thinking_injection(protocol_options)
    if resolved is None:
        if history_text_contains_entml_thinking(history_text):
            return format_thinking_behavior(
                enabled=False, has_tools=has_tools
            )
        return ""
    injection_mode, _ = resolved
    return format_thinking_behavior(
        enabled=True, has_tools=has_tools, injection_mode=injection_mode
    )


def build_entml_thinking_meta_section(
    protocol_options: Optional[Dict[str, Any]] = None,
) -> str:
    """注入 ``max_thinking_length`` + ``thinking_mode``（位于 prompt 最末）。"""
    resolved = resolve_thinking_injection(protocol_options)
    if resolved is None:
        return ""

    injection_mode, max_length = resolved
    meta_lines: List[str] = []
    if max_length is not None:
        meta_lines.append(
            f"<entml:max_thinking_length>{max_length}</entml:max_thinking_length>"
        )
    meta_lines.append(f"<entml:thinking_mode>{injection_mode}</entml:thinking_mode>")
    return "\n".join(meta_lines)


def build_entml_thinking_section(
    protocol_options: Optional[Dict[str, Any]] = None,
    *,
    has_tools: bool = True,
    history_text: str = "",
) -> str:
    """兼容旧调用：``thinking_behavior`` + ``max_thinking_length`` + ``thinking_mode``。"""
    behavior = build_entml_thinking_behavior_section(
        protocol_options, history_text=history_text, has_tools=has_tools
    )
    meta = build_entml_thinking_meta_section(protocol_options)
    if behavior and meta:
        return f"{behavior}\n\n{meta}"
    return behavior or meta
