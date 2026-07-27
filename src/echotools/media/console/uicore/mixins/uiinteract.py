"""ConsoleUI mixins."""
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Optional,
    Sequence,
)

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_types import (
    SpinnerFrames,
    SpinnerStyle,
)
from echotools.media.console.uilayout.ui_misc import (
    Timer,
)
from echotools.media.console.uiwidgets.ui_progress import (
    AsyncProgressBar,
    ProgressBar,
    Spinner,
)
from echotools.media.console.uiwidgets.ui_select import (
    SelectionResult,
)


class _ConsoleUIInteractMixin:
    async def input_async(self, prompt: str = "> ") -> str:
        """异步输入（完全兼容中文输入法）"""
        result = await self._input_handler.readline(prompt)
        self._line_count += 1
        return result

    def input(self, prompt: str = "> ") -> str:
        """同步输入"""
        if self._normal_mode:
            result = input(prompt)
        else:
            _write_flush(self._renderer.render_text_ansi(prompt))
            result = input()
        self._line_count += 1
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # 交互式选择
    # ══════════════════════════════════════════════════════════════════════════

    async def select(
        self,
        title: str,
        options: Sequence[str],
        default_index: int = 0,
    ) -> SelectionResult:
        """异步交互式选择"""
        result = await self._selector.select(title, options, default_index)
        self._line_count += 2
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # 确认对话框
    # ══════════════════════════════════════════════════════════════════════════

    async def confirm(
        self, message: str, default: bool = True,
    ) -> bool:
        """异步确认对话框"""
        result = await self._confirm_dialog.confirm(message, default)
        self._line_count += 1
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # 进度条
    # ══════════════════════════════════════════════════════════════════════════

    def progress(
        self,
        label: str = "",
        total: float = 100.0,
        width: int = 30,
        show_percentage: bool = True,
        show_elapsed: bool = True,
        show_rate: bool = False,
    ) -> ProgressBar:
        """创建进度条（同步上下文管理器）"""
        return ProgressBar(
            self._renderer,
            label=label,
            total=total,
            width=width,
            normal_mode=self._normal_mode,
            show_percentage=show_percentage,
            show_elapsed=show_elapsed,
            show_rate=show_rate,
        )

    def progress_async(
        self,
        label: str = "",
        total: float = 100.0,
        width: int = 30,
        show_percentage: bool = True,
        show_elapsed: bool = True,
        show_rate: bool = False,
    ) -> AsyncProgressBar:
        """创建进度条（异步上下文管理器）"""
        return AsyncProgressBar(
            self._renderer,
            label=label,
            total=total,
            width=width,
            normal_mode=self._normal_mode,
            show_percentage=show_percentage,
            show_elapsed=show_elapsed,
            show_rate=show_rate,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Spinner
    # ══════════════════════════════════════════════════════════════════════════

    def spinner(
        self,
        message: str = "Loading...",
        style: SpinnerStyle = SpinnerStyle.BOUNCE,
        frames: Optional[SpinnerFrames] = None,
    ) -> Spinner:
        """创建 Spinner（支持同步/异步上下文管理器）"""
        return Spinner(
            self._renderer,
            message=message,
            frames=frames or SpinnerFrames.from_style(style),
            normal_mode=self._normal_mode,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 计时器
    # ══════════════════════════════════════════════════════════════════════════

    def timer(self, label: str = "Elapsed") -> Timer:
        """创建计时器（支持同步/异步上下文管理器）"""
        return Timer(
            self._renderer,
            label=label,
            normal_mode=self._normal_mode,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 多行输入
    # ══════════════════════════════════════════════════════════════════════════

    async def multiline_input(
        self,
        prompt: str = "Enter text (empty line to finish):",
        end_marker: str = "",
    ) -> str:
        """异步多行输入"""
        result = await self._multiline_input.read(prompt, end_marker)
        self._line_count += result.count("\n") + 2
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # 分页器
    # ══════════════════════════════════════════════════════════════════════════

    async def page(self, text: str, title: str = "") -> ConsoleUI:
        """分页显示文本"""
        await self._pager.display(text, title)
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 倒计时
    # ══════════════════════════════════════════════════════════════════════════

    async def countdown(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
    ) -> ConsoleUI:
        """异步倒计时"""
        await self._countdown.run(seconds, message)
        return self

    def countdown_sync(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
    ) -> ConsoleUI:
        """同步倒计时"""
        self._countdown.run_sync(seconds, message)
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 命令管理
    # ══════════════════════════════════════════════════════════════════════════

