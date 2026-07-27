"""Timer, notification, key-value list, multiline input, pager, countdown."""
from __future__ import annotations

import asyncio
import math
import time
from typing import ClassVar, Dict, List, Mapping, Optional

from rich.console import Console

from echotools.media.console.uicore.ui_io import (
    _write_flush,
    get_terminal_height,
)
from echotools.media.console.uicore.ui_platform import _get_backend
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import (
    ANSI_CLEAR_SCREEN,
    ANSI_RESET,
    RGB,
    Alignment,
)


def _format_duration(seconds: float) -> str:
    """格式化时间持续"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m{secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h{mins}m"


class Timer:
    """操作计时器 - 支持同步/异步上下文管理器"""

    def __init__(
        self,
        renderer: GradientRenderer,
        label: str = "Elapsed",
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.label = label
        self.normal_mode = normal_mode
        self._start: float = 0.0
        self._end: float = 0.0
        self._running: bool = False

    @property
    def elapsed(self) -> float:
        """获取已用时间（秒）"""
        if self._running:
            return time.monotonic() - self._start
        return self._end - self._start

    @property
    def elapsed_str(self) -> str:
        """获取格式化的已用时间"""
        return _format_duration(self.elapsed)

    def start(self) -> Timer:
        """开始计时"""
        self._start = time.monotonic()
        self._running = True
        return self

    def stop(self) -> Timer:
        """停止计时"""
        self._end = time.monotonic()
        self._running = False
        return self

    def print_elapsed(self) -> None:
        """打印已用时间"""
        elapsed = self.elapsed_str
        if self.normal_mode:
            print(f"{self.label}: {elapsed}")
        else:
            label_ansi = self.renderer.render_text_ansi(f"{self.label}: ")
            r, g, b = self.renderer.theme.accent_start
            _write_flush(
                f"{label_ansi}\033[38;2;{r};{g};{b}m{elapsed}{ANSI_RESET}\n",
            )

    def __enter__(self) -> Timer:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
        self.print_elapsed()

    async def __aenter__(self) -> Timer:
        self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.stop()
        self.print_elapsed()


# ══════════════════════════════════════════════════════════════════════════════
# 通知级别消息
# ══════════════════════════════════════════════════════════════════════════════


class Notification:
    """通知消息组件 - 支持 success/warning/error/info 等级别"""

    ICONS: ClassVar[Dict[str, str]] = {
        "success": "",
        "warning": "",
        "error": "",
        "info": "",
        "debug": "",
    }

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    def _get_color(self, level: str) -> RGB:
        """获取级别对应的颜色"""
        mapping: Dict[str, RGB] = {
            "success": self.renderer.theme.success,
            "warning": self.renderer.theme.warning,
            "error": self.renderer.theme.error,
            "info": self.renderer.theme.info,
            "debug": self.renderer.theme.muted,
        }
        return mapping.get(level, self.renderer.theme.primary_start)

    def show(self, message: str, level: str = "info") -> None:
        """显示通知消息"""
        icon = self.ICONS.get(level, "[*]")
        color = self._get_color(level)

        if self.normal_mode:
            prefix = f"{icon} " if icon else ""
            print(f"{prefix}{message}")
        else:
            r, g, b = color
            colored_msg = self.renderer.render_text_ansi(message)
            if icon:
                colored_icon = f"\033[38;2;{r};{g};{b}m{icon}{ANSI_RESET}"
                _write_flush(f"{colored_icon} {colored_msg}\n")
            else:
                _write_flush(f"{colored_msg}\n")


# ══════════════════════════════════════════════════════════════════════════════
# 键值对列表
# ══════════════════════════════════════════════════════════════════════════════


class KeyValueList:
    """键值对列表 - 美观展示键值对"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
        separator: str = " : ",
        key_width: Optional[int] = None,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode
        self.separator = separator
        self.key_width = key_width

    def render(self, items: Mapping[str, str]) -> int:
        """渲染键值对列表，返回行数"""
        if not items:
            return 0

        max_key_width = self.key_width or max(
            TextUtils.display_width(k) for k in items
        )

        lines = 0
        for key, value in items.items():
            padded_key = TextUtils.pad_to_width(
                key, max_key_width, Alignment.RIGHT,
            )
            if self.normal_mode:
                print(f"{padded_key}{self.separator}{value}")
            else:
                key_ansi = self.renderer.render_text_ansi(
                    padded_key, is_border=True,
                )
                mr, mg, mb = self.renderer.theme.muted
                sep_ansi = (
                    f"\033[38;2;{mr};{mg};{mb}m"
                    f"{self.separator}{ANSI_RESET}"
                )
                val_ansi = self.renderer.render_text_ansi(value)
                _write_flush(f"{key_ansi}{sep_ansi}{val_ansi}\n")
            lines += 1

        return lines


# ══════════════════════════════════════════════════════════════════════════════
# 多行编辑器（简易版）
# ══════════════════════════════════════════════════════════════════════════════


class MultiLineInput:
    """多行输入编辑器"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    async def read(
        self,
        prompt: str = "Enter text (empty line to finish):",
        end_marker: str = "",
    ) -> str:
        """异步读取多行输入"""
        if self.normal_mode:
            print(prompt)
        else:
            _write_flush(f"{self.renderer.render_text_ansi(prompt)}\n")

        lines: List[str] = []
        loop = asyncio.get_running_loop()

        while True:
            if self.normal_mode:
                line = await loop.run_in_executor(
                    None, lambda: input("  "),
                )
            else:
                prefix = self.renderer.render_text_ansi("  ")
                _write_flush(prefix)
                line = await loop.run_in_executor(None, input)

            if end_marker and line.strip() == end_marker:
                break
            if not end_marker and not line.strip():
                break
            lines.append(line)

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 分页器
# ══════════════════════════════════════════════════════════════════════════════


class Pager:
    """文本分页器 - 长文本分页显示"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
        page_size: Optional[int] = None,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode
        self.page_size = page_size

    def _render_page(
        self,
        lines: List[str],
        current_page: int,
        page_size: int,
        title: str,
        total_pages: int,
    ) -> None:
        _write_flush(ANSI_CLEAR_SCREEN)
        if title:
            if self.normal_mode:
                print(f"=== {title} ===")
            else:
                _write_flush(
                    f"{self.renderer.render_text_ansi(f'=== {title} ===')}\n",
                )
        start = current_page * page_size
        end = min(start + page_size, len(lines))
        for line in lines[start:end]:
            if self.normal_mode:
                print(line)
            else:
                self.console.print(self.renderer.render_line(line))
        page_info = f"Page {current_page + 1}/{total_pages}"
        nav_hint = "[q]uit [n]ext [p]rev"
        if self.normal_mode:
            print(f"\n{page_info} | {nav_hint}")
        else:
            mr, mg, mb = self.renderer.theme.muted
            _write_flush(
                f"\n\033[38;2;{mr};{mg};{mb}m"
                f"{page_info} | {nav_hint}{ANSI_RESET}",
            )

    async def display(self, text: str, title: str = "") -> None:
        """分页显示文本"""
        term_height = get_terminal_height()
        page_size = self.page_size or (term_height - 3)
        lines = text.splitlines()
        total_pages = max(1, math.ceil(len(lines) / page_size))
        current_page = 0
        backend = _get_backend()
        loop = asyncio.get_running_loop()

        while True:
            self._render_page(lines, current_page, page_size, title, total_pages)
            key = await loop.run_in_executor(None, backend.getch)
            if key in ("q", "Q", "\x1b"):
                _write_flush(ANSI_CLEAR_SCREEN)
                break
            if key in ("n", "N", " ", "\r") and current_page < total_pages - 1:
                current_page += 1
            elif key in ("p", "P") and current_page > 0:
                current_page -= 1


