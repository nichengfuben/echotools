"""Post-split fixes: trim overlap, split ConsoleUI mixins, write ui.py barrel."""
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "echotools" / "console"
LAYOUT = SRC / "uilayout" / "ui_layout.py"
CONSOLE = SRC / "uicore" / "ui_console.py"

# ── Trim ui_layout.py (remove Timer..Countdown duplicate block) ─────────────
layout_lines = LAYOUT.read_text(encoding="utf-8").splitlines(keepends=True)
timer_start = next(
    i for i, ln in enumerate(layout_lines) if ln.strip() == "class Timer:"
)
col_start = next(
    i for i, ln in enumerate(layout_lines) if ln.strip() == "class ColumnLayout:"
)
trimmed = layout_lines[:timer_start] + layout_lines[col_start:]
LAYOUT.write_text("".join(trimmed), encoding="utf-8")
print(f"ui_layout.py -> {len(trimmed)} lines")

# ── Split ConsoleUI into mixins ────────────────────────────────────────────
lines = CONSOLE.read_text(encoding="utf-8").splitlines(keepends=True)


def find_line(prefix: str, start: int = 0) -> int:
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    raise ValueError(repr(prefix))


class_start = find_line("class ConsoleUI")
print_start = find_line("    def print(", class_start)
stream_start = find_line("    def stream(", print_start)
delete_start = find_line("    def delete_lines(", stream_start)
register_start = find_line("    def register(", delete_start)
repl_start = find_line("    async def repl(", register_start)

shared_imports = lines[:class_start]

SHARED = SRC / "uicore" / "ui_console_shared.py"
SHARED.write_text("".join(shared_imports), encoding="utf-8")

MIXINS = [
    ("ui_console_base.py", "ConsoleUIBase", lines[class_start:print_start]),
    ("ui_console_print.py", "ConsoleUIPrintMixin", lines[print_start:stream_start]),
    ("ui_console_stream.py", "ConsoleUIStreamMixin", lines[stream_start:delete_start]),
    ("ui_console_interact.py", "ConsoleUIInteractMixin", lines[delete_start:register_start]),
    ("ui_console_cmds.py", "ConsoleUICmdsMixin", lines[register_start:repl_start]),
    ("ui_console_repl.py", "ConsoleUIReplMixin", lines[repl_start:]),
]

mixin_header = textwrap.dedent('''\
    """ConsoleUI mixin segment."""
    from __future__ import annotations

    from echotools.media.console.uicore.ui_console_shared import *  # noqa: F403

    ''')

for fname, cls_name, seg in MIXINS:
    body = "".join(seg)
    body = body.replace("class ConsoleUI:", f"class {cls_name}:", 1)
    body = body.replace(") -> ConsoleUI:", ") -> ConsoleUIBase:")
    body = body.replace(") -> ConsoleUI\n", ") -> ConsoleUIBase\n")
    content = mixin_header + body
    (SRC / "uicore" / fname).write_text(content, encoding="utf-8")
    print(f"  {fname}: {len(content.splitlines())} lines")

CONSOLE.write_text(
    textwrap.dedent(
        '''\
        """ConsoleUI main class (mixin composition)."""
        from __future__ import annotations

        from echotools.media.console.uicore.ui_console_base import ConsoleUIBase
        from echotools.media.console.uicore.ui_console_cmds import ConsoleUICmdsMixin
        from echotools.media.console.uicore.ui_console_interact import ConsoleUIInteractMixin
        from echotools.media.console.uicore.ui_console_print import ConsoleUIPrintMixin
        from echotools.media.console.uicore.ui_console_repl import ConsoleUIReplMixin
        from echotools.media.console.uicore.ui_console_stream import ConsoleUIStreamMixin


        class ConsoleUI(
            ConsoleUIBase,
            ConsoleUIPrintMixin,
            ConsoleUIStreamMixin,
            ConsoleUIInteractMixin,
            ConsoleUICmdsMixin,
            ConsoleUIReplMixin,
        ):
            """控制台UI主类 - 高性能异步控制台UI框架"""


        __all__ = ["ConsoleUI"]
        '''
    ),
    encoding="utf-8",
)

# ── ui.py barrel ─────────────────────────────────────────────────────────────
(SRC / "ui.py").write_text(
    textwrap.dedent(
        '''\
        """
        ConsoleUI - 高性能异步控制台UI框架
        """
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
            Alignment,
            BorderChars,
            BorderStyle,
            FontStyle,
            GradientTheme,
            RGB,
            SpinnerFrames,
            SpinnerStyle,
        )
        from echotools.media.console.uilayout.ui_layout import (
            ColumnLayout,
            Divider,
            PanelBuilder,
            TableBuilder,
            TreeNode,
            TreeView,
        )
        from echotools.media.console.uilayout.ui_misc import (
            Countdown,
            KeyValueList,
            MultiLineInput,
            Notification,
            Pager,
            Timer,
        )
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
            """创建 ConsoleUI 实例的便捷工厂函数"""
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
            "ConsoleUI", "create_ui", "FontStyle", "Alignment", "BorderStyle",
            "SpinnerStyle", "GradientTheme", "BorderChars", "SpinnerFrames",
            "SelectionResult", "TreeNode", "GradientRenderer", "StreamWriter",
            "AsyncInput", "BoxBuilder", "AsciiArtBuilder", "TableBuilder",
            "PanelBuilder", "ProgressBar", "AsyncProgressBar", "Spinner",
            "Divider", "Timer", "Notification", "KeyValueList", "MultiLineInput",
            "Pager", "Countdown", "ColumnLayout", "TreeView",
            "InteractiveSelector", "ConfirmDialog", "LogWriter", "FileLogWriter",
            "NullLogWriter", "MultiLogWriter", "CallbackLogWriter", "TextUtils",
            "RGB", "_get_backend", "_normalize_key_event",
        ]
        '''
    ),
    encoding="utf-8",
)

for pkg in ("uicore", "uiwidgets", "uilayout"):
    init = SRC / pkg / "__init__.py"
    if not init.exists():
        init.write_text('"""Console UI subpackage."""\n', encoding="utf-8")

print("fix_console_split.py done")
