"""Console UI public exports."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from echotools.media.console.uicore.ui_console import ConsoleUI
from echotools.media.console.uicore.ui_log import (
    CallbackLogWriter,
    FileLogWriter,
    LogWriter,
    MultiLogWriter,
    NullLogWriter,
)
from echotools.media.console.uicore.ui_platform import (
    _get_backend,
    _normalize_key_event,
)
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import (
    RGB,
    Alignment,
    BorderChars,
    BorderStyle,
    FontStyle,
    GradientTheme,
    SpinnerFrames,
    SpinnerStyle,
)
from echotools.media.console.uilayout.ui_countdown import Countdown
from echotools.media.console.uilayout.ui_layout import Divider
from echotools.media.console.uilayout.ui_misc import (
    KeyValueList,
    MultiLineInput,
    Notification,
    Pager,
    Timer,
)
from echotools.media.console.uilayout.ui_panel import PanelBuilder
from echotools.media.console.uilayout.ui_table import TableBuilder
from echotools.media.console.uilayout.ui_tree import ColumnLayout, TreeNode, TreeView
from echotools.media.console.uiwidgets.ui_box import AsciiArtBuilder, BoxBuilder
from echotools.media.console.uiwidgets.ui_editor import AsyncInput
from echotools.media.console.uiwidgets.ui_progress import (
    AsyncProgressBar,
    ProgressBar,
    Spinner,
)
from echotools.media.console.uiwidgets.ui_select import (
    ConfirmDialog,
    InteractiveSelector,
    SelectionResult,
)
from echotools.media.console.uiwidgets.ui_stream import StreamWriter


def create_ui(
    theme: Optional[GradientTheme] = None,
    log_path: Optional[str] = None,
    char_map: Optional[Dict[str, List[str]]] = None,
    normal_mode: bool = False,
    border_style: BorderStyle = BorderStyle.ROUNDED,
    log_writers: Optional[Sequence[LogWriter]] = None,
) -> ConsoleUI:
    """创建 ConsoleUI 实例的便捷工厂函数。"""
    writers: List[LogWriter] = []
    if log_path:
        writers.append(FileLogWriter(log_path))
    if log_writers:
        writers.extend(log_writers)
    if not writers:
        log_writer: LogWriter = NullLogWriter()
    elif len(writers) == 1:
        log_writer = writers[0]
    else:
        log_writer = MultiLogWriter(*writers)
    return ConsoleUI(
        theme=theme,
        log_writer=log_writer,
        char_map=char_map,
        normal_mode=normal_mode,
        border_style=border_style,
    )


__all__ = [
    "ConsoleUI",
    "create_ui",
    "FontStyle",
    "Alignment",
    "BorderStyle",
    "SpinnerStyle",
    "GradientTheme",
    "BorderChars",
    "SpinnerFrames",
    "SelectionResult",
    "TreeNode",
    "GradientRenderer",
    "StreamWriter",
    "AsyncInput",
    "BoxBuilder",
    "AsciiArtBuilder",
    "TableBuilder",
    "PanelBuilder",
    "ProgressBar",
    "AsyncProgressBar",
    "Spinner",
    "Divider",
    "Timer",
    "Notification",
    "KeyValueList",
    "MultiLineInput",
    "Pager",
    "Countdown",
    "ColumnLayout",
    "TreeView",
    "InteractiveSelector",
    "ConfirmDialog",
    "LogWriter",
    "FileLogWriter",
    "NullLogWriter",
    "MultiLogWriter",
    "CallbackLogWriter",
    "TextUtils",
    "RGB",
    "_get_backend",
    "_normalize_key_event",
]
