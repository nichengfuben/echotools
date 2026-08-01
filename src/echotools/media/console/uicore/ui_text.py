"""Text utilities and gradient renderer."""
from __future__ import annotations

import re
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

from rich.text import Text
from wcwidth import wcswidth, wcwidth

from echotools.media.console.uicore.ui_io import get_terminal_width
from echotools.media.console.uicore.ui_types import (
    ANSI_RESET,
    RGB,
    Alignment,
    GradientTheme,
)


class TextUtils:
    """文本工具类 - 提供文本处理与测量的静态方法集合"""

    _ANSI_PATTERN: ClassVar[re.Pattern] = re.compile(r"\033\[[0-9;]*[a-zA-Z]")

    @staticmethod
    def display_width(text: str) -> int:
        """计算文本显示宽度（考虑全角字符和 ANSI 转义序列）"""
        cleaned = TextUtils.strip_ansi(text)
        width = wcswidth(cleaned)
        if width >= 0:
            return width
        # wcswidth 返回 -1 时逐字符计算
        total = 0
        for char in cleaned:
            w = wcwidth(char)
            total += w if w > 0 else 1
        return total

    @staticmethod
    def strip_ansi(text: str) -> str:
        """移除 ANSI 转义序列"""
        return TextUtils._ANSI_PATTERN.sub("", text)

    @staticmethod
    def pad_to_width(
        text: str,
        width: int,
        align: Alignment = Alignment.LEFT,
    ) -> str:
        """将文本填充到指定显示宽度"""
        current = TextUtils.display_width(text)
        padding = max(0, width - current)
        if align == Alignment.LEFT:
            return text + " " * padding
        if align == Alignment.RIGHT:
            return " " * padding + text
        left = padding // 2
        return " " * left + text + " " * (padding - left)

    @staticmethod
    def truncate(text: str, max_width: int, ellipsis: str = "...") -> str:
        """截断文本到指定宽度"""
        if TextUtils.display_width(text) <= max_width:
            return text
        ellipsis_width = TextUtils.display_width(ellipsis)
        result: List[str] = []
        current_width = 0
        for char in text:
            w = wcwidth(char)
            char_width = w if w > 0 else 1
            if current_width + char_width + ellipsis_width > max_width:
                break
            result.append(char)
            current_width += char_width
        return "".join(result) + ellipsis

    @staticmethod
    def truncate_start(text: str, max_width: int, ellipsis: str = "...") -> str:
        """截断文本：保留末尾，前面加省略号（适用于路径等）"""
        if TextUtils.display_width(text) <= max_width:
            return text
        ellipsis_width = TextUtils.display_width(ellipsis)
        if max_width <= ellipsis_width:
            return TextUtils.truncate(ellipsis, max_width)
        target = max_width - ellipsis_width
        picked: List[str] = []
        current_width = 0
        for char in reversed(text):
            w = wcwidth(char)
            char_width = w if w > 0 else 1
            if current_width + char_width > target:
                break
            picked.append(char)
            current_width += char_width
        return ellipsis + "".join(reversed(picked))

    @staticmethod
    def wrap_text(text: str, width: int) -> List[str]:
        """按显示宽度换行"""
        lines: List[str] = []
        for paragraph in text.splitlines():
            if not paragraph:
                lines.append("")
                continue
            current_line: List[str] = []
            current_width = 0
            for char in paragraph:
                w = wcwidth(char)
                char_width = w if w > 0 else 1
                if current_width + char_width > width and current_line:
                    lines.append("".join(current_line))
                    current_line = []
                    current_width = 0
                current_line.append(char)
                current_width += char_width
            if current_line:
                lines.append("".join(current_line))
        return lines

    @staticmethod
    def center_text(text: str, width: int, fill_char: str = " ") -> str:
        """居中文本"""
        text_width = TextUtils.display_width(text)
        if text_width >= width:
            return text
        total_padding = width - text_width
        left = total_padding // 2
        return fill_char * left + text + fill_char * (total_padding - left)


class GradientRenderer:
    """渐变渲染器 - 核心渲染引擎，负责所有颜色计算与渲染"""

    BORDER_CHARS: ClassVar[frozenset] = frozenset(
        "╚═╝╗║╔╭╮╰╯─│┌┐└┘├┤┬┴┼━┃┏┓┗┛┣┫┳┻╋╠╣╦╩╬",
    )

    def __init__(
        self,
        theme: GradientTheme,
        reference_width: int = 80,
    ) -> None:
        self.theme = theme
        self.reference_width = reference_width
        self._color_cache: Dict[Tuple[RGB, RGB, int], RGB] = {}

    def update_reference_width(self, width: Optional[int] = None) -> None:
        """更新参考宽度"""
        self.reference_width = width if width is not None else get_terminal_width()

    def clear_cache(self) -> None:
        """清空颜色插值缓存"""
        self._color_cache.clear()

    def _interpolate_cached(
        self, start: RGB, end: RGB, factor: float,
    ) -> RGB:
        """带缓存的颜色插值"""
        quantized = int(max(0.0, min(1.0, factor)) * 255)
        key = (start, end, quantized)
        cached = self._color_cache.get(key)
        if cached is not None:
            return cached
        f = quantized / 255.0
        result = (
            int(start[0] + (end[0] - start[0]) * f),
            int(start[1] + (end[1] - start[1]) * f),
            int(start[2] + (end[2] - start[2]) * f),
        )
        self._color_cache[key] = result
        return result

    @staticmethod
    def interpolate(start: RGB, end: RGB, factor: float) -> RGB:
        """颜色插值（纯函数版本）"""
        factor = max(0.0, min(1.0, factor))
        return (
            int(start[0] + (end[0] - start[0]) * factor),
            int(start[1] + (end[1] - start[1]) * factor),
            int(start[2] + (end[2] - start[2]) * factor),
        )

    @staticmethod
    def interpolate_multi(colors: Sequence[RGB], factor: float) -> RGB:
        """多色渐变插值"""
        if not colors:
            return (255, 255, 255)
        if len(colors) == 1:
            return colors[0]
        factor = max(0.0, min(1.0, factor))
        segment_count = len(colors) - 1
        scaled = factor * segment_count
        index = min(int(scaled), segment_count - 1)
        local_factor = scaled - index
        return GradientRenderer.interpolate(
            colors[index], colors[index + 1], local_factor,
        )

    def _diagonal_factor(self, col: int, row: int, max_diag: int) -> float:
        """计算对角线渐变因子"""
        return (col + row) / max_diag if max_diag > 0 else 0.0

    def color_for_char(
        self, index: int, total: int, is_border: bool = False,
    ) -> RGB:
        """计算单个字符的渐变颜色"""
        ref_len = max(total, 30)
        factor = index / (ref_len - 1) if ref_len > 1 else 0.0
        if is_border:
            return self._interpolate_cached(
                self.theme.border_start, self.theme.border_end, factor,
            )
        return self._interpolate_cached(
            self.theme.primary_start, self.theme.primary_end, factor,
        )

    def color_for_accent(self, index: int, total: int) -> RGB:
        """计算强调色渐变"""
        ref_len = max(total, 30)
        factor = index / (ref_len - 1) if ref_len > 1 else 0.0
        return self._interpolate_cached(
            self.theme.accent_start, self.theme.accent_end, factor,
        )

    def rgb_fg(self, r: int, g: int, b: int) -> str:
        """RGB 转 ANSI 前景色序列"""
        return f"\033[38;2;{r};{g};{b}m"

    def rgb_bg(self, r: int, g: int, b: int) -> str:
        """RGB 转 ANSI 背景色序列"""
        return f"\033[48;2;{r};{g};{b}m"

    def render_text_ansi(
        self,
        text: str,
        start_index: int = 0,
        total_length: Optional[int] = None,
        is_border: bool = False,
    ) -> str:
        """渲染文本为 ANSI 转义字符串（水平渐变）"""
        if not text:
            return ""
        total = total_length or (start_index + len(text))
        ref_len = max(total, 30)
        start = self.theme.border_start if is_border else self.theme.primary_start
        end = self.theme.border_end if is_border else self.theme.primary_end
        parts: List[str] = []
        for i, char in enumerate(text):
            factor = (start_index + i) / (ref_len - 1) if ref_len > 1 else 0.0
            r, g, b = self._interpolate_cached(start, end, factor)
            parts.append(f"\033[38;2;{r};{g};{b}m{char}")
        parts.append(ANSI_RESET)
        return "".join(parts)

    def render_text_solid(self, text: str, color: RGB) -> str:
        """渲染纯色文本"""
        r, g, b = color
        return f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}"

    def _banner_metrics(self, lines: Sequence[str]) -> int:
        width = max((len(line) for line in lines), default=0)
        ref_width = max(width, self.reference_width // 2)
        return ref_width + len(lines) - 2

    def _banner_color(
        self,
        char: str,
        col_idx: int,
        row_idx: int,
        max_diag: int,
        *,
        use_border_colors: bool,
    ) -> RGB:
        is_border = char in self.BORDER_CHARS
        factor = self._diagonal_factor(col_idx, row_idx, max_diag)
        if is_border and use_border_colors:
            return self._interpolate_cached(
                self.theme.border_start, self.theme.border_end, factor,
            )
        return self._interpolate_cached(
            self.theme.primary_start, self.theme.primary_end, factor,
        )

    def render_banner(
        self,
        text: str,
        use_border_colors: bool = True,
        row_offset: int = 0,
    ) -> Text:
        """渲染横幅文本（多行对角线渐变，使用 Rich Text）"""
        lines = text.splitlines()
        if not lines:
            return Text()
        max_diag = self._banner_metrics(lines)
        result = Text()
        for row_idx, line in enumerate(lines):
            actual_row = row_offset + row_idx
            for col_idx, char in enumerate(line):
                color = self._banner_color(
                    char, col_idx, actual_row, max_diag,
                    use_border_colors=use_border_colors,
                )
                result.append(
                    char, style=f"rgb({color[0]},{color[1]},{color[2]})",
                )
            if row_idx < len(lines) - 1:
                result.append("\n")
        return result

    def render_banner_ansi(
        self,
        text: str,
        use_border_colors: bool = True,
        row_offset: int = 0,
    ) -> str:
        """渲染横幅为 ANSI 字符串（不受 Rich/NO_COLOR 影响，供 print 使用）。"""
        lines = text.splitlines()
        if not lines:
            return ""
        max_diag = self._banner_metrics(lines)
        parts: List[str] = []
        for row_idx, line in enumerate(lines):
            actual_row = row_offset + row_idx
            for col_idx, char in enumerate(line):
                if char == " ":
                    parts.append(char)
                    continue
                r, g, b = self._banner_color(
                    char, col_idx, actual_row, max_diag,
                    use_border_colors=use_border_colors,
                )
                parts.append(f"\033[38;2;{r};{g};{b}m{char}")
            parts.append(ANSI_RESET)
            if row_idx < len(lines) - 1:
                parts.append("\n")
        return "".join(parts)

    def render_line(
        self,
        text: str,
        col_offset: int = 0,
        row: int = 0,
        is_border: bool = False,
    ) -> Text:
        """渲染单行文本（Rich Text，对角线渐变）"""
        result = Text()
        ref_width = max(len(text) + col_offset, self.reference_width // 2)
        max_diag = ref_width + 20
        for i, char in enumerate(text):
            factor = self._diagonal_factor(col_offset + i, row, max_diag)
            if is_border or char in self.BORDER_CHARS:
                color = self._interpolate_cached(
                    self.theme.border_start, self.theme.border_end, factor,
                )
            else:
                color = self._interpolate_cached(
                    self.theme.primary_start, self.theme.primary_end, factor,
                )
            result.append(
                char, style=f"rgb({color[0]},{color[1]},{color[2]})",
            )
        return result

    def render_progress_bar(
        self,
        progress: float,
        width: int = 30,
        filled_char: str = "━",
        empty_char: str = "─",
        head_char: str = "╸",
    ) -> str:
        """渲染渐变进度条（ANSI）"""
        progress = max(0.0, min(1.0, progress))
        filled_count = int(width * progress)
        empty_count = width - filled_count
        parts: List[str] = []
        for i in range(filled_count):
            factor = i / max(width - 1, 1)
            r, g, b = self._interpolate_cached(
                self.theme.primary_start, self.theme.primary_end, factor,
            )
            parts.append(f"\033[38;2;{r};{g};{b}m{filled_char}")
        if filled_count < width:
            factor = filled_count / max(width - 1, 1)
            r, g, b = self._interpolate_cached(
                self.theme.primary_start, self.theme.primary_end, factor,
            )
            parts.append(f"\033[38;2;{r};{g};{b}m{head_char}")
            empty_count -= 1
        if empty_count > 0:
            mr, mg, mb = self.theme.muted
            parts.append(f"\033[38;2;{mr};{mg};{mb}m{empty_char * empty_count}")
        parts.append(ANSI_RESET)
        return "".join(parts)


