from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

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

_THINKING_BEHAVIOR_ON = """\
Your default is to think before it answers to give the person the best possible answer. Even for questions that might seem obvious, if there are any signs of lurking complexity, You takes the time to open up an extended thinking block and dig in to make sure it's got the details figured out and isn't just pattern-matching to the familiar. At the end of its thinking, You restates which language it should respond in.

You MUST output a <entml:thinking> block before any other content in every reply. Only after that block, output your visible reply and/or <entml:invoke> tool call(s). Never skip the thinking block."""

_THINKING_BEHAVIOR_AUTO = """\
You decide whether extended thinking helps for each reply. When the question has hidden complexity, when tool results need interpretation, or when you are uncertain, open a <entml:thinking> block before continuing and strongly prefer to do so rather than guessing.

After completed tool turns appear in conversation history inside <tool> blocks (for example a line like [tool_name: value] followed by its result), strongly consider outputting a <entml:thinking> block before your next visible reply or tool call."""


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


def _uses_forced_thinking_behavior(injection_mode: str) -> bool:
    return injection_mode != "auto"


def _format_thinking_behavior(injection_mode: str) -> str:
    body = _THINKING_BEHAVIOR_ON if _uses_forced_thinking_behavior(injection_mode) else _THINKING_BEHAVIOR_AUTO
    return f"<thinking_behavior>\n{body}\n</thinking_behavior>"


def build_entml_thinking_section(
    protocol_options: Optional[Dict[str, Any]] = None,
) -> str:
    """按思考挡位构建注入块：thinking_mode + max_thinking_length + thinking_behavior。"""
    resolved = resolve_thinking_injection(protocol_options)
    if resolved is None:
        return ""

    injection_mode, max_length = resolved
    lines = [f"<entml:thinking_mode>{injection_mode}</entml:thinking_mode>"]
    if max_length is not None:
        lines.append(f"<entml:max_thinking_length>{max_length}</entml:max_thinking_length>")
    lines.append("")
    lines.append(_format_thinking_behavior(injection_mode))
    return "\n".join(lines)
