from __future__ import annotations

"""递归字典合并工具。"""

from typing import Any, Dict

__all__ = ["merge_dicts"]


def merge_dicts(
    target: Dict[str, Any],
    source: Dict[str, Any],
    *,
    skip_keys: tuple = ("version",),
) -> None:
    """递归将 source 中 target 缺少的键补进 target（就地修改）。

    Args:
        target: 目标字典（就地修改）。
        source: 源字典（只读）。
        skip_keys: 不参与合并的键名。
    """
    for key, value in source.items():
        if key in skip_keys:
            continue
        if key not in target:
            target[key] = value
        elif isinstance(value, dict) and isinstance(target[key], dict):
            merge_dicts(target[key], value, skip_keys=skip_keys)
