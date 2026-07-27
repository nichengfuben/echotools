"""Progress bar and spinner."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, List, Optional

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_text import GradientRenderer
from echotools.media.console.uicore.ui_types import (
    ANSI_CLEAR_LINE,
    ANSI_HIDE_CURSOR,
    ANSI_RESET,
    ANSI_SHOW_CURSOR,
    SpinnerFrames,
)


class ProgressBar:
    """
    渐变进度条 - 支持同步和异步更新

    用法：
      with ui.progress("Processing", total=100) as pb:
        for i in range(100):
          pb.advance(1)

      async with ui.progress_async("Loading", total=50) as pb:
        async for item in source:
          await pb.advance_async(1)
    """

    def __init__(
        self,
        renderer: GradientRenderer,
        label: str = "",
        total: float = 100.0,
        width: int = 30,
        normal_mode: bool = False,
        show_percentage: bool = True,
        show_elapsed: bool = True,
        show_rate: bool = False,
    ) -> None:
        self.renderer = renderer
        self.label = label
        self.total = total
        self.width = width
        self.normal_mode = normal_mode
        self.show_percentage = show_percentage
        self.show_elapsed = show_elapsed
        self.show_rate = show_rate
        self._current: float = 0.0
        self._start_time: float = 0.0
        self._finished: bool = False

    def start(self) -> None:
        """开始进度条"""
        self._start_time = time.monotonic()
        self._current = 0.0
        self._finished = False
        self._draw()

    def advance(self, amount: float = 1.0) -> None:
        """推进进度"""
        self._current = min(self._current + amount, self.total)
        self._draw()

    async def advance_async(self, amount: float = 1.0) -> None:
        """异步推进进度"""
        self.advance(amount)
        await asyncio.sleep(0)

    def set_progress(self, value: float) -> None:
        """直接设置进度值"""
        self._current = max(0.0, min(value, self.total))
        self._draw()

    def finish(self) -> None:
        """完成进度条"""
        self._current = self.total
        self._finished = True
        self._draw()
        _write_flush("\n")

    def _append_stats(self, parts: List[str], progress: float, elapsed: float) -> None:
        if self.show_percentage:
            pct = f" {progress * 100:5.1f}%"
            if not self.normal_mode:
                r, g, b = self.renderer.theme.primary_end
                pct = f"\033[38;2;{r};{g};{b}m{pct}{ANSI_RESET}"
            parts.append(pct)
        if self.show_elapsed:
            elapsed_str = _format_duration(elapsed)
            if not self.normal_mode:
                mr, mg, mb = self.renderer.theme.muted
                elapsed_str = f"\033[38;2;{mr};{mg};{mb}m {elapsed_str}{ANSI_RESET}"
            else:
                elapsed_str = f" {elapsed_str}"
            parts.append(elapsed_str)
        if self.show_rate and elapsed > 0:
            rate = self._current / elapsed
            rate_str = f" ({rate:.1f}/s)"
            if not self.normal_mode:
                mr, mg, mb = self.renderer.theme.muted
                rate_str = f"\033[38;2;{mr};{mg};{mb}m{rate_str}{ANSI_RESET}"
            parts.append(rate_str)

    def _draw(self) -> None:
        """绘制进度条"""
        progress = self._current / self.total if self.total > 0 else 0.0
        elapsed = time.monotonic() - self._start_time
        parts: List[str] = [ANSI_HIDE_CURSOR, ANSI_CLEAR_LINE]

        if self.label:
            if self.normal_mode:
                parts.append(f"{self.label} ")
            else:
                parts.append(self.renderer.render_text_ansi(self.label + " "))

        if self.normal_mode:
            filled = int(self.width * progress)
            head = ">" if self.width - filled > 0 else ""
            empty = " " * max(0, self.width - filled - 1)
            parts.append(f"[{'=' * filled}{head}{empty}]")
        else:
            parts.append(self.renderer.render_progress_bar(progress, self.width))

        self._append_stats(parts, progress, elapsed)
        parts.append(ANSI_SHOW_CURSOR)
        _write_flush("".join(parts))

    def __enter__(self) -> ProgressBar:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        if not self._finished:
            self.finish()


class AsyncProgressBar(ProgressBar):
    """异步上下文管理器版本的进度条"""

    async def __aenter__(self) -> AsyncProgressBar:
        self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if not self._finished:
            self.finish()


# ══════════════════════════════════════════════════════════════════════════════
# Spinner（加载动画）
# ══════════════════════════════════════════════════════════════════════════════


class Spinner:
    """
    渐变加载动画 - 支持同步和异步上下文管理器

    用法：
      async with ui.spinner("Loading...") as sp:
        await do_work()
        sp.update_message("Almost done...")
    """

    def __init__(
        self,
        renderer: GradientRenderer,
        message: str = "Loading...",
        frames: Optional[SpinnerFrames] = None,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.message = message
        self.frames = frames or SpinnerFrames.BRAILLE
        self.normal_mode = normal_mode
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._thread: Optional[threading.Thread] = None
        self._frame_index: int = 0
        self._lock = threading.Lock()

    def update_message(self, message: str) -> None:
        """更新显示消息"""
        with self._lock:
            self.message = message

    async def _animate_async(self) -> None:
        """异步动画循环"""
        while self._running:
            self._draw_frame()
            await asyncio.sleep(self.frames.interval)

    def _animate_sync(self) -> None:
        """同步动画循环（在线程中运行）"""
        while self._running:
            self._draw_frame()
            time.sleep(self.frames.interval)

    def _draw_frame(self) -> None:
        """绘制当前帧"""
        with self._lock:
            frame = self.frames.frames[
                self._frame_index % len(self.frames.frames)
            ]
            msg = self.message

        self._frame_index += 1

        if self.normal_mode:
            line = f"\r{frame} {msg}"
        else:
            factor = (self._frame_index % 60) / 59.0
            r, g, b = self.renderer._interpolate_cached(
                self.renderer.theme.primary_start,
                self.renderer.theme.primary_end,
                factor,
            )
            colored_frame = f"\033[38;2;{r};{g};{b}m{frame}{ANSI_RESET}"
            colored_msg = self.renderer.render_text_ansi(msg)
            line = f"\r{ANSI_CLEAR_LINE}{colored_frame} {colored_msg}"

        _write_flush(f"{ANSI_HIDE_CURSOR}{line}")

    def start(self) -> None:
        """启动动画（同步，在后台线程运行）"""
        self._running = True
        self._frame_index = 0
        self._thread = threading.Thread(
            target=self._animate_sync, daemon=True,
        )
        self._thread.start()

    def stop(self, final_message: str = "") -> None:
        """停止动画（同步）"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        _write_flush(f"{ANSI_CLEAR_LINE}{ANSI_SHOW_CURSOR}")
        if final_message:
            if self.normal_mode:
                _write_flush(f"\r{final_message}\n")
            else:
                r, g, b = self.renderer.theme.success
                _write_flush(
                    f"\r\033[38;2;{r};{g};{b}m"
                    f"{final_message}{ANSI_RESET}\n",
                )

    async def start_async(self) -> None:
        """启动异步动画"""
        self._running = True
        self._frame_index = 0
        self._task = asyncio.create_task(self._animate_async())

    async def stop_async(self, final_message: str = "") -> None:
        """停止异步动画"""
        self._running = False
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

        _write_flush(f"{ANSI_CLEAR_LINE}{ANSI_SHOW_CURSOR}")
        if final_message:
            if self.normal_mode:
                _write_flush(f"\r{final_message}\n")
            else:
                r, g, b = self.renderer.theme.success
                _write_flush(
                    f"\r\033[38;2;{r};{g};{b}m"
                    f"{final_message}{ANSI_RESET}\n",
                )

    def __enter__(self) -> Spinner:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()

    async def __aenter__(self) -> Spinner:
        await self.start_async()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop_async()

