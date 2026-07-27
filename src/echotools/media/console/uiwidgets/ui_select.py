"""Interactive selector and confirm dialog."""
from __future__ import annotations

import asyncio
from typing import NamedTuple, Sequence

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_platform import (
    _get_backend,
    _normalize_key_event,
)
from echotools.media.console.uicore.ui_text import GradientRenderer
from echotools.media.console.uicore.ui_types import (
    ANSI_CLEAR_LINE,
    ANSI_HIDE_CURSOR,
    ANSI_MOVE_UP,
    ANSI_RESET,
)


class SelectionResult(NamedTuple):
    """选择结果"""
    index: int
    value: str


class InteractiveSelector:
    """交互式选择器 - 支持上下键选择"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    def _handle_select_key(
        self,
        vk: str,
        options: Sequence[str],
        current: int,
        total_lines: int,
    ) -> tuple[int, Optional[SelectionResult]]:
        if vk == "return":
            self._clear_options(total_lines)
            self._draw_final_selection(options[current])
            return current, SelectionResult(current, options[current])
        if vk == "up":
            current = (current - 1) % len(options)
            self._clear_options(total_lines)
            self._draw_options(options, current)
            return current, None
        if vk == "down":
            current = (current + 1) % len(options)
            self._clear_options(total_lines)
            self._draw_options(options, current)
            return current, None
        if vk == "escape":
            self._clear_options(total_lines)
            return current, SelectionResult(-1, "")
        if vk == "interrupt":
            self._clear_options(total_lines)
            raise KeyboardInterrupt
        return current, None

    async def select(
        self,
        title: str,
        options: Sequence[str],
        default_index: int = 0,
    ) -> SelectionResult:
        """异步选择（上下键移动，回车确认）"""
        if not options:
            raise ValueError("Options list cannot be empty")

        current = max(0, min(default_index, len(options) - 1))
        total_lines = len(options)
        backend = _get_backend()
        loop = asyncio.get_running_loop()

        if self.normal_mode:
            print(title)
        else:
            _write_flush(f"{self.renderer.render_text_ansi(title)}\n")

        self._draw_options(options, current)

        try:
            while True:
                raw_events = await loop.run_in_executor(
                    None, backend.read_key_events,
                )
                for raw in raw_events:
                    event = _normalize_key_event(raw)
                    current, picked = self._handle_select_key(
                        event.get("vk", ""), options, current, total_lines,
                    )
                    if picked is not None:
                        return picked

                if not raw_events:
                    await asyncio.sleep(0.01)

        except BaseException:
            self._clear_options(total_lines)
            raise

    def _draw_options(
        self, options: Sequence[str], selected: int,
    ) -> None:
        """绘制选项列表"""
        parts: List[str] = []
        for i, opt in enumerate(options):
            if i == selected:
                r, g, b = self.renderer.theme.primary_start
                parts.append(
                    f"\033[38;2;{r};{g};{b}m > {opt}{ANSI_RESET}\n",
                )
            else:
                mr, mg, mb = self.renderer.theme.muted
                parts.append(
                    f"\033[38;2;{mr};{mg};{mb}m   {opt}{ANSI_RESET}\n",
                )
        _write_flush(ANSI_HIDE_CURSOR + "".join(parts))

    def _clear_options(self, count: int) -> None:
        """清除选项显示"""
        _write_flush((ANSI_MOVE_UP + ANSI_CLEAR_LINE) * count)

    def _draw_final_selection(self, selected: str) -> None:
        """绘制最终选择结果"""
        r, g, b = self.renderer.theme.success
        _write_flush(f"\033[38;2;{r};{g};{b}m -> {selected}{ANSI_RESET}\n")


# ══════════════════════════════════════════════════════════════════════════════
# 确认对话框
# ══════════════════════════════════════════════════════════════════════════════


class ConfirmDialog:
    """确认对话框"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    async def confirm(
        self, message: str, default: bool = True,
    ) -> bool:
        """异步确认对话框"""
        suffix = " [Y/n] " if default else " [y/N] "
        full_prompt = message + suffix

        if self.normal_mode:
            _write_flush(full_prompt)
        else:
            _write_flush(self.renderer.render_text_ansi(full_prompt))

        backend = _get_backend()
        loop = asyncio.get_running_loop()

        while True:
            raw_events = await loop.run_in_executor(
                None, backend.read_key_events,
            )
            for raw in raw_events:
                event = _normalize_key_event(raw)
                vk = event.get("vk", "")
                char = event.get("char", "")

                if vk == "return":
                    self._show_result(default)
                    return default

                if vk == "interrupt":
                    _write_flush(f"{ANSI_RESET}\n")
                    raise KeyboardInterrupt

                if char and char.lower() in ("y", "n"):
                    result = char.lower() == "y"
                    self._show_result(result)
                    return result

            if not raw_events:
                await asyncio.sleep(0.01)

    def _show_result(self, result: bool) -> None:
        """显示确认结果"""
        label = "Y" if result else "N"
        color = self.renderer.theme.success if result else self.renderer.theme.error
        r, g, b = color
        _write_flush(f"\033[38;2;{r};{g};{b}m{label}{ANSI_RESET}\n")

