from pathlib import Path

layout = Path("src/echotools/media/console/uilayout/ui_layout.py")
lines = layout.read_text(encoding="utf-8").splitlines(keepends=True)

idx_table = next(i for i, l in enumerate(lines) if l.startswith("class TableBuilder"))
idx_panel = next(i for i, l in enumerate(lines) if l.startswith("class PanelBuilder"))
idx_divider = next(i for i, l in enumerate(lines) if l.startswith("class Divider"))

table_part = lines[idx_table:idx_panel]
panel_part = lines[idx_panel:idx_divider]
divider_part = lines[idx_divider:]

Path("src/echotools/media/console/uilayout/ui_table.py").write_text(
    '"""Table builder."""\nfrom __future__ import annotations\n\n'
    "from typing import List, Optional, Sequence\n\n"
    "from rich.console import Console\n"
    "from rich.text import Text\n\n"
    "from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils\n"
    "from echotools.media.console.uicore.ui_types import Alignment, BorderChars, BorderStyle\n\n"
    + "".join(table_part),
    encoding="utf-8",
)
Path("src/echotools/media/console/uilayout/ui_panel.py").write_text(
    '"""Panel builder."""\nfrom __future__ import annotations\n\n'
    "from typing import Optional\n\n"
    "from rich.console import Console\n"
    "from rich.text import Text\n\n"
    "from echotools.media.console.uicore.ui_io import get_terminal_width\n"
    "from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils\n"
    "from echotools.media.console.uicore.ui_types import BorderChars, BorderStyle\n\n"
    + "".join(panel_part),
    encoding="utf-8",
)
layout.write_text(
    '"""Divider component."""\nfrom __future__ import annotations\n\n'
    "from typing import Optional\n\n"
    "from rich.console import Console\n\n"
    "from echotools.media.console.uicore.ui_io import get_terminal_width\n"
    "from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils\n\n"
    + "".join(divider_part),
    encoding="utf-8",
)
