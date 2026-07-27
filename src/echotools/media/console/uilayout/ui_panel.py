"""Panel builder."""
from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.text import Text

from echotools.media.console.uicore.ui_io import get_terminal_width
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import BorderChars, BorderStyle


def _panel_inner_width(
    content_lines: list[str],
    title: str,
    subtitle: str,
    width: Optional[int],
    padding: int,
) -> int:
    if width is not None:
        return width - 2 - padding * 2
    max_content = max(
        (TextUtils.display_width(line) for line in content_lines),
        default=0,
    )
    title_w = TextUtils.display_width(title) + 4 if title else 0
    sub_w = TextUtils.display_width(subtitle) + 4 if subtitle else 0
    return min(
        max(max_content, title_w, sub_w, 20),
        get_terminal_width() - 4,
    )


class PanelBuilder:
    """面板构建器 - 带标题和边框的内容区域"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        border_style: BorderStyle = BorderStyle.ROUNDED,
        normal_mode: bool = False,
        padding: int = 1,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.border_style = border_style
        self.normal_mode = normal_mode
        self.padding = padding

    def _top_border(self, chars: BorderChars, title: str, box_inner: int) -> str:
        if not title:
            return f"{chars.top_left}{chars.horizontal * box_inner}{chars.top_right}"
        td = f" {title} "
        td_w = TextUtils.display_width(td)
        return (
            f"{chars.top_left}{chars.horizontal * 2}{td}"
            f"{chars.horizontal * max(0, box_inner - 2 - td_w)}{chars.top_right}"
        )

    def _bottom_border(self, chars: BorderChars, subtitle: str, box_inner: int) -> str:
        if not subtitle:
            return (
                f"{chars.bottom_left}{chars.horizontal * box_inner}{chars.bottom_right}"
            )
        sd = f" {subtitle} "
        sd_w = TextUtils.display_width(sd)
        return (
            f"{chars.bottom_left}"
            f"{chars.horizontal * max(0, box_inner - 2 - sd_w)}"
            f"{sd}{chars.horizontal * 2}{chars.bottom_right}"
        )

    def _render_wrapped_line(
        self,
        chars: BorderChars,
        wl: str,
        inner_width: int,
        box_inner: int,
        row: int,
    ) -> None:
        row_rich = Text()
        row_rich.append_text(
            self.renderer.render_line(chars.vertical, row=row, is_border=True),
        )
        row_rich.append(" " * self.padding)
        row_rich.append_text(self.renderer.render_line(wl, row=row))
        pad_right = inner_width - TextUtils.display_width(wl)
        row_rich.append(" " * max(0, pad_right))
        row_rich.append(" " * self.padding)
        row_rich.append_text(
            self.renderer.render_line(
                chars.vertical, col_offset=box_inner + 1, row=row, is_border=True,
            ),
        )
        self.console.print(row_rich)

    def render(
        self,
        content: str,
        title: str = "",
        subtitle: str = "",
        width: Optional[int] = None,
        row_offset: int = 0,
    ) -> int:
        """渲染面板，返回行数"""
        chars = BorderChars.from_style(self.border_style)
        content_lines = content.strip().splitlines()
        inner_width = _panel_inner_width(
            content_lines, title, subtitle, width, self.padding,
        )
        box_inner = inner_width + self.padding * 2
        current_row = row_offset
        lines_rendered = 0

        top_str = self._top_border(chars, title, box_inner)
        self.console.print(
            self.renderer.render_line(top_str, row=current_row, is_border=True),
        )
        current_row += 1
        lines_rendered += 1

        for line_text in content_lines:
            wrapped = TextUtils.wrap_text(line_text, inner_width) or [""]
            for wl in wrapped:
                self._render_wrapped_line(
                    chars, wl, inner_width, box_inner, current_row,
                )
                current_row += 1
                lines_rendered += 1

        bottom_str = self._bottom_border(chars, subtitle, box_inner)
        self.console.print(
            self.renderer.render_line(bottom_str, row=current_row, is_border=True),
        )
        return lines_rendered + 1
