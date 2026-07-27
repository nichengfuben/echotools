"""Table builder."""
from __future__ import annotations

from typing import List, Optional, Sequence

from rich.console import Console
from rich.text import Text

from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import Alignment, BorderChars, BorderStyle


def _table_separator(
    chars: BorderChars,
    col_widths: Sequence[int],
    padding: int,
    left: str,
    mid: str,
    right: str,
) -> str:
    parts = [chars.horizontal * (w + padding * 2) for w in col_widths]
    return left + mid.join(parts) + right


def _table_col_widths(
    header_row: Sequence[str],
    all_rows: Sequence[Sequence[str]],
    col_count: int,
    min_col_width: int,
    has_headers: bool,
) -> List[int]:
    widths: List[int] = []
    for c in range(col_count):
        header_w = TextUtils.display_width(header_row[c]) if has_headers else 0
        data_w = max(
            (TextUtils.display_width(row[c]) for row in all_rows),
            default=0,
        )
        widths.append(max(header_w, data_w, min_col_width))
    return widths


class TableBuilder:
    """渐变表格构建器。"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        headers: Optional[Sequence[str]] = None,
        border_style: BorderStyle = BorderStyle.ROUNDED,
        normal_mode: bool = False,
        min_col_width: int = 3,
        padding: int = 1,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.headers = list(headers) if headers else []
        self.border_style = border_style
        self.normal_mode = normal_mode
        self.min_col_width = min_col_width
        self.padding = padding
        self._rows: List[List[str]] = []
        self._alignments: List[Alignment] = []

    def add_row(self, row: Sequence[str]) -> TableBuilder:
        self._rows.append(list(row))
        return self

    def add_rows(self, rows: Sequence[Sequence[str]]) -> TableBuilder:
        for row in rows:
            self._rows.append(list(row))
        return self

    def set_alignments(self, *alignments: Alignment) -> TableBuilder:
        self._alignments = list(alignments)
        return self

    def _print_border(
        self,
        chars: BorderChars,
        col_widths: Sequence[int],
        row: int,
        left: str,
        mid: str,
        right: str,
    ) -> None:
        line = _table_separator(chars, col_widths, self.padding, left, mid, right)
        self.console.print(self.renderer.render_line(line, row=row, is_border=True))

    def _render_header(
        self,
        chars: BorderChars,
        header_row: Sequence[str],
        col_widths: Sequence[int],
        alignments: Sequence[Alignment],
        row: int,
    ) -> None:
        pad = " " * self.padding
        ht = Text()
        ht.append_text(
            self.renderer.render_line(chars.vertical, row=row, is_border=True),
        )
        for hdr, width, align in zip(header_row, col_widths, alignments):
            ht.append(pad)
            padded = TextUtils.pad_to_width(hdr, width, align)
            for ci, ch in enumerate(padded):
                factor = ci / max(width - 1, 1)
                r, g, b = self.renderer._interpolate_cached(
                    self.renderer.theme.accent_start,
                    self.renderer.theme.accent_end,
                    factor,
                )
                ht.append(ch, style=f"bold rgb({r},{g},{b})")
            ht.append(pad)
            ht.append_text(
                self.renderer.render_line(chars.vertical, row=row, is_border=True),
            )
        self.console.print(ht)

    def _render_data_row(
        self,
        chars: BorderChars,
        row_data: Sequence[str],
        col_widths: Sequence[int],
        alignments: Sequence[Alignment],
        row: int,
    ) -> None:
        pad = " " * self.padding
        rt = Text()
        rt.append_text(
            self.renderer.render_line(chars.vertical, row=row, is_border=True),
        )
        for i, (cell, width, align) in enumerate(
            zip(row_data, col_widths, alignments),
        ):
            rt.append(pad)
            padded = TextUtils.pad_to_width(cell, width, align)
            rt.append_text(
                self.renderer.render_line(
                    padded, col_offset=i * 10, row=row,
                ),
            )
            rt.append(pad)
            rt.append_text(
                self.renderer.render_line(chars.vertical, row=row, is_border=True),
            )
        self.console.print(rt)

    def _render_body(
        self,
        chars: BorderChars,
        all_rows: Sequence[Sequence[str]],
        header_row: Sequence[str],
        col_count: int,
        row_offset: int,
    ) -> int:
        col_widths = _table_col_widths(
            header_row, all_rows, col_count, self.min_col_width, bool(self.headers),
        )
        alignments = list(self._alignments) + [Alignment.LEFT] * (
            col_count - len(self._alignments)
        )
        current_row = row_offset
        lines = 0
        self._print_border(
            chars, col_widths, current_row,
            chars.top_left, chars.t_top or chars.horizontal, chars.top_right,
        )
        current_row += 1
        lines += 1
        if self.headers:
            self._render_header(chars, header_row, col_widths, alignments, current_row)
            current_row += 1
            lines += 1
            self._print_border(
                chars, col_widths, current_row,
                chars.t_left or chars.vertical,
                chars.cross or chars.horizontal,
                chars.t_right or chars.vertical,
            )
            current_row += 1
            lines += 1
        for row_data in all_rows:
            self._render_data_row(chars, row_data, col_widths, alignments, current_row)
            current_row += 1
            lines += 1
        self._print_border(
            chars, col_widths, current_row,
            chars.bottom_left, chars.t_bottom or chars.horizontal, chars.bottom_right,
        )
        return lines + 1

    def render(self, row_offset: int = 0) -> int:
        """渲染表格，返回占用的行数"""
        chars = BorderChars.from_style(self.border_style)
        col_count = max(
            len(self.headers),
            max((len(row) for row in self._rows), default=0),
        )
        if col_count == 0:
            return 0
        all_rows = [row + [""] * (col_count - len(row)) for row in self._rows]
        header_row = self.headers + [""] * (col_count - len(self.headers))
        return self._render_body(chars, all_rows, header_row, col_count, row_offset)
