"""Split console/ui.py into submodules under uicore/, uiwidgets/, uilayout/."""
from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "echotools" / "media" / "console"
UI = SRC / "ui.py"
BACKUP = SRC / "ui_monolith.py.bak"

lines = UI.read_text(encoding="utf-8").splitlines(keepends=True)


def sl(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def w(rel: str, header: str, body: str) -> None:
    p = SRC / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    content = header + body
    p.write_text(content, encoding="utf-8")
    print(f"  {rel}: {len(content.splitlines())} lines")


# backup original
if not BACKUP.exists():
    shutil.copy2(UI, BACKUP)

print("Writing modules...")

w(
    "uicore/ui_types.py",
    textwrap.dedent('''\
    """Console UI enums, constants, and data types."""
    from __future__ import annotations

    import sys
    from dataclasses import dataclass
    from enum import Enum, auto
    from typing import ClassVar, Dict, Final, Tuple

    RGB = Tuple[int, int, int]
    IS_WINDOWS: Final[bool] = sys.platform == "win32"
    IS_MACOS: Final[bool] = sys.platform == "darwin"
    IS_LINUX: Final[bool] = sys.platform.startswith("linux")

    ANSI_RESET: Final[str] = "\\033[0m"
    ANSI_HIDE_CURSOR: Final[str] = "\\033[?25l"
    ANSI_SHOW_CURSOR: Final[str] = "\\033[?25h"
    ANSI_CLEAR_LINE: Final[str] = "\\r\\033[K"
    ANSI_MOVE_UP: Final[str] = "\\033[F"
    ANSI_CLEAR_SCREEN: Final[str] = "\\033[2J\\033[H"
    ANSI_BOLD: Final[str] = "\\033[1m"

    '''),
    sl(540, 764),
)

w(
    "uicore/ui_log.py",
    textwrap.dedent('''\
    """Log writer protocol and implementations."""
    from __future__ import annotations

    import datetime
    import threading
    from dataclasses import dataclass, field
    from typing import Callable, Protocol, Tuple, runtime_checkable

    '''),
    sl(771, 828),
)

w(
    "uicore/ui_io.py",
    textwrap.dedent('''\
    """Terminal I/O helpers."""
    from __future__ import annotations

    import os
    import sys

    '''),
    sl(835, 854),
)

w(
    "uicore/ui_text.py",
    textwrap.dedent('''\
    """Text utilities and gradient renderer."""
    from __future__ import annotations

    import re
    from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

    from rich.text import Text
    from wcwidth import wcswidth, wcwidth

    from echotools.media.console.uicore.ui_io import get_terminal_width
    from echotools.media.console.uicore.ui_types import (
        ANSI_RESET,
        Alignment,
        GradientTheme,
        RGB,
    )

    '''),
    sl(862, 1211),
)

w(
    "uiwidgets/ui_box.py",
    textwrap.dedent('''\
    """Box and ASCII art builders."""
    from __future__ import annotations

    from typing import Dict, List, Optional, Tuple

    from rich.text import Text

    from echotools.media.console.uicore.ui_io import get_terminal_width
    from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
    from echotools.media.console.uicore.ui_types import BorderChars, BorderStyle

    '''),
    sl(1218, 1398),
)

w(
    "uiwidgets/ui_stream.py",
    textwrap.dedent('''\
    """Stream writer for character-by-character output."""
    from __future__ import annotations

    import asyncio
    import sys
    import time
    from typing import AsyncIterator, Iterator, Tuple

    from echotools.media.console.uicore.ui_io import _write_flush
    from echotools.media.console.uicore.ui_text import GradientRenderer
    from echotools.media.console.uicore.ui_types import ANSI_RESET, RGB

    '''),
    sl(1405, 1476),
)

w(
    "uiwidgets/ui_editor.py",
    textwrap.dedent('''\
    """Line editor and async input."""
    from __future__ import annotations

    import asyncio
    from dataclasses import dataclass, field
    from pathlib import Path
    from typing import Callable, List, Optional

    from rich.console import Console

    from echotools.media.console.uicore.ui_io import _write_flush
    from echotools.media.console.uicore.ui_platform import (
        _get_backend,
        _normalize_key_event,
    )
    from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
    from echotools.media.console.uicore.ui_types import (
        ANSI_HIDE_CURSOR,
        ANSI_RESET,
        ANSI_SHOW_CURSOR,
    )

    '''),
    sl(1483, 1817),
)

w(
    "uiwidgets/ui_select.py",
    textwrap.dedent('''\
    """Interactive selector and confirm dialog."""
    from __future__ import annotations

    import asyncio
    from typing import NamedTuple, Sequence

    from echotools.media.console.uicore.ui_io import _write_flush
    from echotools.media.console.uicore.ui_platform import (
        _get_backend,
        _normalize_key_event,
    )
    from echotools.media.console.uicore.ui_text import GradientRenderer
    from echotools.media.console.uicore.ui_types import (
        ANSI_CLEAR_LINE,
        ANSI_HIDE_CURSOR,
        ANSI_MOVE_UP,
        ANSI_RESET,
    )

    '''),
    sl(1824, 1992),
)

w(
    "uiwidgets/ui_progress.py",
    textwrap.dedent('''\
    """Progress bar and spinner."""
    from __future__ import annotations

    import asyncio
    import threading
    import time
    from typing import Any, List, Optional

    from echotools.media.console.uicore.ui_io import _write_flush
    from echotools.media.console.uicore.ui_text import GradientRenderer
    from echotools.media.console.uicore.ui_types import (
        ANSI_CLEAR_LINE,
        ANSI_HIDE_CURSOR,
        ANSI_RESET,
        ANSI_SHOW_CURSOR,
        SpinnerFrames,
        SpinnerStyle,
    )

    '''),
    sl(1999, 2280),
)

w(
    "uilayout/ui_layout.py",
    textwrap.dedent('''\
    """Table, panel, divider, column layout, tree view."""
    from __future__ import annotations

    from dataclasses import dataclass, field
    from typing import List, Optional, Sequence

    from rich.console import Console
    from rich.text import Text

    from echotools.media.console.uicore.ui_io import get_terminal_width
    from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
    from echotools.media.console.uicore.ui_types import Alignment, BorderChars, BorderStyle

    '''),
    sl(2287, 3193),
)

w(
    "uilayout/ui_misc.py",
    textwrap.dedent('''\
    """Timer, notification, key-value list, multiline input, pager, countdown."""
    from __future__ import annotations

    import asyncio
    import math
    import time
    from typing import Awaitable, Callable, ClassVar, Dict, List, Mapping, Optional

    from rich.console import Console

    from echotools.media.console.uicore.ui_io import (
        _write_flush,
        get_terminal_height,
        get_terminal_width,
    )
    from echotools.media.console.uicore.ui_platform import _get_backend
    from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
    from echotools.media.console.uicore.ui_types import (
        ANSI_CLEAR_LINE,
        ANSI_CLEAR_SCREEN,
        ANSI_RESET,
        Alignment,
        RGB,
    )

    '''),
    sl(2663, 3046),
)

w(
    "uicore/ui_console.py",
    textwrap.dedent('''\
    """ConsoleUI main class."""
    from __future__ import annotations

    import asyncio
    import sys
    import time
    from pathlib import Path
    from typing import (
        Any,
        AsyncIterator,
        Awaitable,
        Callable,
        Dict,
        Iterator,
        Mapping,
        Optional,
        Sequence,
        Set,
    )

    from rich.console import Console

    from echotools.media.console.uicore.ui_io import _write_flush
    from echotools.media.console.uicore.ui_log import LogWriter, NullLogWriter
    from echotools.media.console.uicore.ui_text import GradientRenderer
    from echotools.media.console.uicore.ui_types import (
        ANSI_RESET,
        BorderStyle,
        FontStyle,
        GradientTheme,
        RGB,
        SpinnerFrames,
        SpinnerStyle,
    )
    from echotools.media.console.uilayout.ui_layout import (
        PanelBuilder,
        TableBuilder,
        TreeNode,
    )
    from echotools.media.console.uilayout.ui_misc import (
        Countdown,
        KeyValueList,
        MultiLineInput,
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
    from echotools.media.console.uilayout.ui_layout import Divider, ColumnLayout, TreeView
    from echotools.media.console.uilayout.ui_misc import Notification

    '''),
    sl(3200, 4139),
)

print("Done extraction. ui_platform.py and ui.py barrel written separately.")
