"""Terminal I/O helpers."""
from __future__ import annotations

import os
import sys


def get_terminal_width() -> int:
    """安全获取终端宽度"""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def get_terminal_height() -> int:
    """安全获取终端高度"""
    try:
        return os.get_terminal_size().lines
    except OSError:
        return 24


def _write_flush(text: str) -> None:
    """写入 stdout 并立即刷新"""
    sys.stdout.write(text)
    sys.stdout.flush()
