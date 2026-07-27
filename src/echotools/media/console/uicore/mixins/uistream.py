"""ConsoleUI mixins."""
from __future__ import annotations

import asyncio
import sys
import time
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Iterator,
)

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_types import (
    ANSI_CLEAR_LINE,
    ANSI_CLEAR_SCREEN,
    ANSI_MOVE_UP,
    ANSI_RESET,
)


class _ConsoleUIStreamMixin:
    def stream(
        self,
        text: str,
        delay: float = 0.02,
        newline: bool = True,
    ) -> ConsoleUI:
        """同步流式输出（逐字符渐变）"""
        self._stream_writer.reset()
        lines = self._stream_writer.write_text(text, delay)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        self._log_writer.write(text)
        return self

    async def stream_async(
        self,
        text: str,
        delay: float = 0.02,
        newline: bool = True,
    ) -> ConsoleUI:
        """异步流式输出（逐字符渐变）"""
        self._stream_writer.reset()
        lines = await self._stream_writer.write_text_async(text, delay)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        self._log_writer.write(text)
        return self

    def stream_iter(
        self,
        iterable: Iterator[str],
        delay: float = 0.0,
        newline: bool = True,
    ) -> ConsoleUI:
        """从迭代器流式输出（适用于 LLM 响应等）"""
        self._stream_writer.reset()
        lines = 0
        for chunk in iterable:
            for char in chunk:
                if char == "\n":
                    _write_flush(f"{ANSI_RESET}\n")
                    lines += 1
                    self._stream_writer._char_index = 0
                else:
                    self._stream_writer.write_char(char, 100)
                if delay > 0:
                    time.sleep(delay)
            sys.stdout.flush()

        _write_flush(ANSI_RESET)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        return self

    async def stream_aiter(
        self,
        iterable: AsyncIterator[str],
        delay: float = 0.0,
        newline: bool = True,
    ) -> ConsoleUI:
        """从异步迭代器流式输出"""
        self._stream_writer.reset()
        lines = 0
        async for chunk in iterable:
            for char in chunk:
                if char == "\n":
                    _write_flush(f"{ANSI_RESET}\n")
                    lines += 1
                    self._stream_writer._char_index = 0
                else:
                    self._stream_writer.write_char(char, 100)
                if delay > 0:
                    await asyncio.sleep(delay)
            sys.stdout.flush()

        _write_flush(ANSI_RESET)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 行操作（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def delete_lines(self, count: int = 1) -> ConsoleUI:
        """删除指定行数"""
        if count <= 0:
            return self
        _write_flush((ANSI_MOVE_UP + ANSI_CLEAR_LINE) * count)
        self._line_count = max(0, self._line_count - count)
        return self

    def clear_output(self) -> ConsoleUI:
        """清除所有已跟踪的输出"""
        return self.delete_lines(self._line_count)

    def clear_line(self) -> ConsoleUI:
        """清除当前行"""
        _write_flush(ANSI_CLEAR_LINE)
        return self

    def clear_screen(self) -> ConsoleUI:
        """清屏"""
        _write_flush(ANSI_CLEAR_SCREEN)
        self._line_count = 0
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 输入方法
    # ══════════════════════════════════════════════════════════════════════════

