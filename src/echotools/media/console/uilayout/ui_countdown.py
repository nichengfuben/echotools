"""Countdown component."""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_text import GradientRenderer
from echotools.media.console.uicore.ui_types import ANSI_CLEAR_LINE, ANSI_RESET


class Countdown:
    """倒计时组件"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    def _write_tick(self, text: str, remaining: int, total: int) -> None:
        if self.normal_mode:
            _write_flush(f"\r{text} ")
            return
        factor = 1.0 - (remaining / total)
        r, g, b = self.renderer._interpolate_cached(
            self.renderer.theme.warning,
            self.renderer.theme.success,
            factor,
        )
        _write_flush(
            f"{ANSI_CLEAR_LINE}"
            f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}",
        )

    async def run(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
        on_tick: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> None:
        """异步倒计时"""
        for remaining in range(seconds, 0, -1):
            self._write_tick(message.format(seconds=remaining), remaining, seconds)
            if on_tick is not None:
                await on_tick(remaining)
            await asyncio.sleep(1.0)
        _write_flush(ANSI_CLEAR_LINE)

    def run_sync(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
    ) -> None:
        """同步倒计时"""
        for remaining in range(seconds, 0, -1):
            self._write_tick(message.format(seconds=remaining), remaining, seconds)
            time.sleep(1.0)
        _write_flush(ANSI_CLEAR_LINE)
