"""Divider component."""
from __future__ import annotations

from typing import Optional

from rich.console import Console

from echotools.media.console.uicore.ui_io import get_terminal_width
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils


class Divider:
    """渐变分隔线"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode

    def render(
        self,
        char: str = "─",
        width: Optional[int] = None,
        title: str = "",
        row: int = 0,
    ) -> None:
        """渲染分隔线"""
        actual_width = width or get_terminal_width()

        if title:
            td = f" {title} "
            td_w = TextUtils.display_width(td)
            left_len = max(0, (actual_width - td_w) // 2)
            right_len = max(0, actual_width - td_w - left_len)
            line = char * left_len + td + char * right_len
        else:
            line = char * actual_width

        if self.normal_mode:
            print(line)
        else:
            self.console.print(
                self.renderer.render_line(line, row=row, is_border=True),
            )

