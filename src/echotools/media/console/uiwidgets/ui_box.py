"""Box and ASCII art builders."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from rich.text import Text

from echotools.media.console.uicore.ui_io import get_terminal_width
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import BorderChars, BorderStyle


def _box_processed_lines(text: str, prefix: str) -> List[str]:
    lines = text.strip().splitlines()
    if not lines:
        return []
    prefix_width = TextUtils.display_width(prefix)
    processed: List[str] = []
    for idx, line in enumerate(lines):
        content = line.strip()
        if not content:
            processed.append("")
            continue
        if idx == 0 and prefix:
            processed.append(f"{prefix} {content}")
        else:
            indent = " " * (prefix_width + 1) if prefix else ""
            processed.append(f"{indent}{content}")
    return processed


def _box_content_width(
    processed: List[str], title: str, min_width: int,
) -> int:
    max_content_width = max(
        (TextUtils.display_width(line) for line in processed), default=0,
    )
    if title:
        max_content_width = max(
            max_content_width, TextUtils.display_width(title) + 4,
        )
    max_content_width = max(max_content_width, min_width)
    term_width = get_terminal_width()
    return min(max(max_content_width, 20), max(term_width - 4, 8))


class BoxBuilder:
    """盒子构建器 - 支持多种边框样式"""

    def __init__(
        self,
        renderer: GradientRenderer,
        padding: int = 1,
        border_style: BorderStyle = BorderStyle.ROUNDED,
    ) -> None:
        self.renderer = renderer
        self.padding = padding
        self.border_style = border_style

    def _box_borders(
        self, chars: BorderChars, title: str, box_inner_width: int,
    ) -> tuple[str, str]:
        if title:
            title_decorated = f" {title} "
            title_dw = TextUtils.display_width(title_decorated)
            top_str = (
                f"{chars.top_left}{chars.horizontal * 2}{title_decorated}"
                f"{chars.horizontal * max(0, box_inner_width - 2 - title_dw)}"
                f"{chars.top_right}"
            )
        else:
            top_str = (
                f"{chars.top_left}{chars.horizontal * box_inner_width}{chars.top_right}"
            )
        bottom_str = (
            f"{chars.bottom_left}{chars.horizontal * box_inner_width}"
            f"{chars.bottom_right}"
        )
        return top_str, bottom_str

    def _append_row(
        self,
        result: List[Text],
        chars: BorderChars,
        content: str,
        row: int,
        max_content_width: int,
        box_inner_width: int,
    ) -> None:
        line = Text()
        line.append_text(
            self.renderer.render_line(chars.vertical, row=row, is_border=True),
        )
        line.append(" " * self.padding)
        line.append(content)
        pad_right = max(0, max_content_width - TextUtils.display_width(content))
        line.append(" " * pad_right)
        line.append(" " * self.padding)
        line.append_text(
            self.renderer.render_line(
                chars.vertical, col_offset=box_inner_width + 1, row=row, is_border=True,
            ),
        )
        result.append(line)

    def build(
        self,
        text: str,
        prefix: str = "",
        row_offset: int = 0,
        title: str = "",
        min_width: int = 0,
    ) -> List[Text]:
        """构建文本盒子"""
        processed = _box_processed_lines(text, prefix)
        if not processed:
            return []

        chars = BorderChars.from_style(self.border_style)
        max_content_width = _box_content_width(processed, title, min_width)
        display_lines: List[str] = []
        for line in processed:
            if not line or TextUtils.display_width(line) <= max_content_width:
                display_lines.append(line)
            else:
                display_lines.extend(
                    TextUtils.wrap_text(line, max_content_width) or [""],
                )

        box_inner_width = max_content_width + self.padding * 2
        top_str, bottom_str = self._box_borders(chars, title, box_inner_width)
        result: List[Text] = [
            self.renderer.render_line(top_str, row=row_offset, is_border=True),
        ]

        for idx, content in enumerate(display_lines):
            self._append_row(
                result, chars, content, row_offset + idx + 1,
                max_content_width, box_inner_width,
            )

        result.append(
            self.renderer.render_line(
                bottom_str, row=row_offset + len(display_lines) + 1, is_border=True,
            ),
        )
        return result


class AsciiArtBuilder:
    """ASCII 艺术字构建器"""

    def __init__(
        self,
        renderer: GradientRenderer,
        char_map: Dict[str, List[str]],
    ) -> None:
        self.renderer = renderer
        self.char_map = char_map

    def build(
        self,
        text: str,
        row_offset: int = 0,
        max_width: Optional[int] = None,
    ) -> Tuple[Text, int]:
        """构建 ASCII 艺术字；超宽时按终端列数自动换行"""
        text = text.upper()
        line_count = 6
        lines = [""] * line_count

        for char in text:
            if char in self.char_map:
                char_lines = self.char_map[char]
                for i in range(min(line_count, len(char_lines))):
                    lines[i] += char_lines[i]
            else:
                for i in range(line_count):
                    lines[i] += " "

        term_width = max_width if max_width is not None else get_terminal_width()
        content_width = max(term_width - 2, 8)
        wrapped_lines: List[str] = []
        for line in lines:
            if TextUtils.display_width(line) <= content_width:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(
                    TextUtils.wrap_text(line, content_width) or [""],
                )

        banner = self.renderer.render_banner(
            "\n".join(wrapped_lines),
            use_border_colors=True,
            row_offset=row_offset,
        )
        return banner, len(wrapped_lines)
