"""Rich-backed CLI output wrapper with selectable themes."""

from __future__ import annotations

import sys
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from echotools.media.console.uilayout.ui_bridge import (
    create_themed_ui,
    get_utf8_stdout,
    render_gradient_banner,
    render_text_lines,
)
from echotools.media.console.uiwidgets.ui_themes import (
    ThemePreset,
    get_rich_theme,
    get_theme_preset,
    normalize_theme_name,
)


def get_console(*, theme_name: str | None = None, themed: bool = True) -> Console:
    kwargs: dict = {}
    if themed:
        kwargs["theme"] = get_rich_theme(theme_name)
    if sys.platform == "win32" and "pytest" not in sys.modules:
        kwargs["file"] = get_utf8_stdout()
        kwargs["force_terminal"] = True
    return Console(**kwargs)


class RichCLI:
    """Terminal output helper: echotools ConsoleUI + Rich markup."""

    def __init__(
        self,
        theme_name: str | None = None,
        console: Optional[Console] = None,
    ) -> None:
        resolved = normalize_theme_name(theme_name)
        self._preset: ThemePreset = get_theme_preset(resolved)
        self._ui = create_themed_ui(theme_name=resolved)
        self.console = console or get_console(theme_name=resolved)

    @property
    def theme_name(self) -> str:
        return self._preset.name

    def banner(self, text: str = "APP") -> None:
        lines = render_text_lines(text)
        print(render_gradient_banner(lines, theme_name=self.theme_name))

    def header(self, title: str) -> None:
        preset = self._preset
        panel = Panel(
            "",
            title=f"[{preset.header}]{title}[/{preset.header}]",
            border_style=preset.border,
            expand=False,
        )
        self.console.print(panel)

    def success(self, msg: str) -> None:
        self.console.print(f"[bold green][OK][/bold green] {msg}")

    def error(self, msg: str) -> None:
        self.console.print(f"[bold red][FAIL][/bold red] {msg}")

    def warning(self, msg: str) -> None:
        self.console.print(f"[bold yellow][!][/bold yellow]  {msg}")

    def info(self, msg: str) -> None:
        self.console.print(f"[bold cyan][i][/bold cyan]  {msg}")

    def table(
        self,
        headers: list[str],
        rows: list[list[str]],
        title: Optional[str] = None,
    ) -> None:
        preset = self._preset
        tbl = Table(
            title=title,
            show_header=True,
            header_style=f"bold white on {preset.border}",
            border_style=preset.border,
            title_style=preset.header,
            expand=False,
        )
        for h in headers:
            tbl.add_column(h, style=preset.column)
        for row in rows:
            tbl.add_row(*row)
        self.console.print(tbl)

    def divider(self) -> None:
        self._ui.divider()

    def heavy_divider(self) -> None:
        self._ui.divider(char="═", title="")

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.console.print(*args, **kwargs)

    def newline(self) -> None:
        self.console.print()
