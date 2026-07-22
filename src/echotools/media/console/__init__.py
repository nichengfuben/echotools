from __future__ import annotations

"""echotools.media.console：终端 ConsoleUI 框架。

渐变文本、圆角边框、ASCII 艺术字、表格/面板、异步输入与 Spinner。
依赖：rich、wcwidth（``pip install echotools[console]``）。
"""

from echotools.media.console.charmap import char_map
from echotools.media.console.spinner import Clock, Spinner
from echotools.media.console.ui import (
    Alignment,
    BorderStyle,
    ConsoleUI,
    FileLogWriter,
    FontStyle,
    GradientTheme,
    TextUtils,
    create_ui,
    _get_backend,
    _normalize_key_event,
)

__all__ = [
    "Alignment",
    "BorderStyle",
    "Clock",
    "ConsoleUI",
    "FileLogWriter",
    "FontStyle",
    "GradientTheme",
    "Spinner",
    "TextUtils",
    "char_map",
    "create_ui",
    "_get_backend",
    "_normalize_key_event",
]
