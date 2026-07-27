"""Stream writer for character-by-character output."""
from __future__ import annotations

import asyncio
import sys
import time
from typing import AsyncIterator, Iterator, Tuple

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_text import GradientRenderer
from echotools.media.console.uicore.ui_types import ANSI_RESET, RGB


class StreamWriter:
    """流式输出器 - 支持逐字符渐变输出"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode
        self._char_index: int = 0

    def reset(self) -> None:
        """重置内部状态"""
        self._char_index = 0

    def write_char(self, char: str, total_length: int = 100) -> None:
        """写入单个字符（带渐变色）"""
        if self.normal_mode or char == "\n":
            sys.stdout.write(char)
        else:
            r, g, b = self.renderer.color_for_char(
                self._char_index, total_length,
            )
            sys.stdout.write(f"\033[38;2;{r};{g};{b}m{char}")
        sys.stdout.flush()
        self._char_index += 1

    def write_text(self, text: str, delay: float = 0.02) -> int:
        """同步流式写入文本，返回换行数"""
        lines = 0
        total = len(text)
        for char in text:
            if char == "\n":
                _write_flush(f"{ANSI_RESET}\n")
                lines += 1
                self._char_index = 0
            else:
                self.write_char(char, total)
            if delay > 0:
                time.sleep(delay)
        _write_flush(ANSI_RESET)
        return lines

    async def write_text_async(self, text: str, delay: float = 0.02) -> int:
        """异步流式写入文本，返回换行数"""
        lines = 0
        total = len(text)
        for char in text:
            if char == "\n":
                _write_flush(f"{ANSI_RESET}\n")
                lines += 1
                self._char_index = 0
            else:
                self.write_char(char, total)
            if delay > 0:
                await asyncio.sleep(delay)
        _write_flush(ANSI_RESET)
        return lines

    def iter_chars(self, text: str) -> Iterator[Tuple[str, RGB]]:
        """迭代字符及其对应颜色"""
        total = len(text)
        for i, char in enumerate(text):
            yield char, self.renderer.color_for_char(i, total)

    async def aiter_chars(self, text: str) -> AsyncIterator[Tuple[str, RGB]]:
        """异步迭代字符及其对应颜色"""
        total = len(text)
        for i, char in enumerate(text):
            yield char, self.renderer.color_for_char(i, total)

