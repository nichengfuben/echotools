from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

_DESC_KEY = "description"
_TIMEOUT_KEY = "timeout"

_MANGLED_PARAM_JSON_TAIL_RE = re.compile(
    r'"\s*,\s*"description"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"timeout"\s*:\s*(\d+)\s*\}\}?\s*$',
    re.DOTALL,
)


def _param_value_is_json_container(value: str) -> bool:
    stripped = (value or "").lstrip()
    return bool(stripped) and stripped[0] in "{["


def _match_schema_key_prefix(
    text: str,
    pos: int,
    *,
    allowed: Tuple[str, ...] = (_DESC_KEY, _TIMEOUT_KEY),
) -> Optional[Tuple[str, int]]:
    """匹配 schema 键。

    返回 ``("<key>"|"partial", new_pos)``；已偏离则 ``None``。
    """
    if pos >= len(text):
        return ("partial", pos)
    for key in allowed:
        if text.startswith(key, pos):
            return (key, pos + len(key))
    remain = text[pos:]
    for key in allowed:
        if key.startswith(remain):
            return ("partial", len(text))
    return None


def _consume_json_string_body(text: str, pos: int) -> Tuple[int, bool]:
    """从 JSON 字符串内容起点消费（不含开引号）。返回 ``(new_pos, closed)``。"""
    i = pos
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text):
                return len(text), False
            i += 2
            continue
        if ch == '"':
            return i + 1, True
        i += 1
    return len(text), False


def _match_mangled_description_field(suffix: str, pos: int) -> Optional[int]:
    """匹配 mangled 尾缀中的 description 字段；成功返回新 pos，partial 返回 len(suffix)。"""
    key_match = _match_schema_key_prefix(suffix, pos, allowed=(_DESC_KEY,))
    if key_match is None:
        return None
    key, pos = key_match
    if key == "partial":
        return pos if pos == len(suffix) else None
    if key != _DESC_KEY:
        return None
    if pos >= len(suffix):
        return pos
    if suffix[pos] != '"':
        return None
    pos += 1
    m_colon = re.match(r"\s*:\s*", suffix[pos:])
    if not m_colon:
        return pos if re.match(r"\s*$", suffix[pos:]) else None
    pos += m_colon.end()
    if pos >= len(suffix):
        return pos
    if suffix[pos] != '"':
        return None
    pos += 1
    pos, closed = _consume_json_string_body(suffix, pos)
    if not closed:
        return pos if pos == len(suffix) else None
    return pos


def _match_mangled_timeout_field(suffix: str, pos: int) -> Optional[int]:
    """匹配 mangled 尾缀中的 timeout 字段；成功返回新 pos。"""
    if pos >= len(suffix):
        return pos
    if suffix[pos] != '"':
        return None
    pos += 1
    key2 = _match_schema_key_prefix(suffix, pos, allowed=(_TIMEOUT_KEY,))
    if key2 is None:
        return None
    key2_name, pos = key2
    if key2_name == "partial":
        return pos if pos == len(suffix) else None
    if key2_name != _TIMEOUT_KEY:
        return None
    if pos >= len(suffix):
        return pos
    if suffix[pos] != '"':
        return None
    pos += 1
    m_colon2 = re.match(r"\s*:\s*", suffix[pos:])
    if not m_colon2:
        return pos if re.match(r"\s*$", suffix[pos:]) else None
    pos += m_colon2.end()
    m_num2 = re.match(r"\d*", suffix[pos:])
    assert m_num2 is not None
    pos += m_num2.end()
    return pos if re.match(r"\s*\}{0,2}\s*$", suffix[pos:]) else None


def _is_mangled_schema_tail_suffix(suffix: str) -> bool:
    """``suffix`` 是否整段为 mangled schema 尾缀（允许流式未写完）。

    必须以 ``description``（或其真前缀）起头；禁止把文末单独的
    ``", "timeout": N`` 当成尾缀（避免截断正文 JSON）。
    """
    if not suffix:
        return False
    m = re.match(r'^"\s*,\s*"', suffix)
    if not m:
        return False
    pos = _match_mangled_description_field(suffix, m.end())
    if pos is None:
        return False
    if pos == len(suffix):
        return True
    m_rest = re.match(r"\s*,\s*", suffix[pos:])
    if not m_rest:
        return re.match(r"\s*\}{0,2}\s*$", suffix[pos:]) is not None
    pos += m_rest.end()
    timeout_pos = _match_mangled_timeout_field(suffix, pos)
    return timeout_pos is not None


def _ambiguous_comma_hold_end(value: str) -> int:
    """值以 ``",`` / ``", "`` 结尾且下一键未明时，返回应保留到的终点（含引号）。"""
    m = re.search(r'"\s*,\s*"?$', value)
    if not m:
        return -1
    return m.start() + 1


def _find_mangled_schema_tail_start(value: str) -> int:
    """返回 mangled 尾缀起点；无则 -1。"""
    starts = [m.start() for m in re.finditer(r'"\s*,\s*"', value)]
    for start in starts:
        if _is_mangled_schema_tail_suffix(value[start:]):
            return start
    hold = _ambiguous_comma_hold_end(value)
    if hold >= 0:
        return hold - 1
    return -1


def mangled_json_param_tail_in_progress(value: str) -> bool:
    """值末尾正在形成 mangled schema 尾缀（尚未收齐）时抑制 partial_json 增长。"""
    if not value or _param_value_is_json_container(value):
        return False
    start = _find_mangled_schema_tail_start(value)
    if start < 0:
        return False
    if _MANGLED_PARAM_JSON_TAIL_RE.search(value[start:]):
        return False
    return True


def split_mangled_json_param_tail(
    value: str,
    *,
    param_name: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """模型把 ``", "description": ..., "timeout": ...}}`` 误写入 parameter 值时的拆分。"""
    _ = param_name
    if not value:
        return value, {}
    if _param_value_is_json_container(value):
        try:
            json.loads(value)
            return value, {}
        except json.JSONDecodeError:
            return value, {}

    match = _MANGLED_PARAM_JSON_TAIL_RE.search(value)
    if match:
        return value[: match.start() + 1], {
            "description": match.group(1),
            "timeout": int(match.group(2)),
        }

    start = _find_mangled_schema_tail_start(value)
    if start < 0:
        return value, {}
    return value[: start + 1], {}
