"""ConsoleUI mixins."""
from __future__ import annotations

from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
)

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

from rich.console import Console

from echotools.media.console.uicore.ui_log import LogWriter, NullLogWriter
from echotools.media.console.uicore.ui_text import GradientRenderer
from echotools.media.console.uicore.ui_types import (
    BorderStyle,
    GradientTheme,
)
from echotools.media.console.uilayout.ui_countdown import Countdown
from echotools.media.console.uilayout.ui_layout import Divider
from echotools.media.console.uilayout.ui_misc import (
    KeyValueList,
    MultiLineInput,
    Notification,
    Pager,
)
from echotools.media.console.uilayout.ui_panel import PanelBuilder
from echotools.media.console.uilayout.ui_tree import ColumnLayout, TreeView
from echotools.media.console.uiwidgets.ui_box import AsciiArtBuilder, BoxBuilder
from echotools.media.console.uiwidgets.ui_editor import AsyncInput
from echotools.media.console.uiwidgets.ui_select import (
    ConfirmDialog,
    InteractiveSelector,
)
from echotools.media.console.uiwidgets.ui_stream import StreamWriter


class _ConsoleUIBase:
    def __init__(
        self,
        theme: Optional[GradientTheme] = None,
        log_writer: Optional[LogWriter] = None,
        char_map: Optional[Dict[str, List[str]]] = None,
        normal_mode: bool = False,
        border_style: BorderStyle = BorderStyle.ROUNDED,
    ) -> None:
        self._theme = theme or GradientTheme.default()
        self._log_writer: LogWriter = log_writer or NullLogWriter()
        self._char_map = char_map or {}
        self._normal_mode = normal_mode
        self._border_style = border_style

        self._console = Console(highlight=False)
        self._renderer = GradientRenderer(self._theme)
        self._renderer.update_reference_width()
        self._init_subcomponents(border_style)
        self._line_count: int = 0
        self._commands: Dict[str, Dict[str, Any]] = {}

    def _init_subcomponents(self, border_style: BorderStyle) -> None:
        self._box_builder = BoxBuilder(
            self._renderer, border_style=border_style,
        )
        self._art_builder = AsciiArtBuilder(self._renderer, self._char_map)
        self._input_handler = AsyncInput(
            self._renderer, self._console, self._normal_mode,
            completer=self._complete_command,
            history_path=Path.home() / ".star_cursor_history",
        )
        self._stream_writer = StreamWriter(self._renderer, self._normal_mode)
        self._selector = InteractiveSelector(self._renderer, self._normal_mode)
        self._confirm_dialog = ConfirmDialog(self._renderer, self._normal_mode)
        self._notification = Notification(self._renderer, self._normal_mode)
        self._divider = Divider(
            self._renderer, self._console, self._normal_mode,
        )
        self._panel_builder = PanelBuilder(
            self._renderer, self._console, border_style, self._normal_mode,
        )
        self._kv_list = KeyValueList(self._renderer, self._normal_mode)
        self._multiline_input = MultiLineInput(self._renderer, self._normal_mode)
        self._pager = Pager(
            self._renderer, self._console, self._normal_mode,
        )
        self._countdown = Countdown(self._renderer, self._normal_mode)
        self._column_layout = ColumnLayout(
            self._renderer, self._console, self._normal_mode,
        )
        self._tree_view = TreeView(
            self._renderer, self._console, self._normal_mode,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 属性
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def line_count(self) -> int:
        return self._line_count

    @property
    def theme(self) -> GradientTheme:
        return self._theme

    @property
    def commands(self) -> Dict[str, Dict[str, Any]]:
        return self._commands.copy()

    def _complete_command(self, prefix: str) -> List[str]:
        has_slash = prefix.startswith("/")
        search = prefix if has_slash else "/" + prefix
        matches = [k for k in self._commands if k.startswith(search)]
        return matches if has_slash else [k[1:] for k in matches]

    @property
    def renderer(self) -> GradientRenderer:
        return self._renderer

    @property
    def console(self) -> Console:
        return self._console

    @property
    def is_normal_mode(self) -> bool:
        return self._normal_mode

    # ══════════════════════════════════════════════════════════════════════════
    # 配置方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def set_theme(self, theme: GradientTheme) -> ConsoleUI:
        self._theme = theme
        self._renderer.theme = theme
        self._renderer.clear_cache()
        return self

    def set_normal_mode(self, enabled: bool) -> ConsoleUI:
        """设置普通模式（无颜色渐变）"""
        self._normal_mode = enabled
        # 批量更新所有子组件
        components = [
            self._input_handler, self._stream_writer, self._selector,
            self._confirm_dialog, self._notification, self._divider,
            self._panel_builder, self._kv_list, self._multiline_input,
            self._pager, self._countdown, self._column_layout,
            self._tree_view,
        ]
        for comp in components:
            comp.normal_mode = enabled
        return self

    def set_char_map(self, char_map: Dict[str, List[str]]) -> ConsoleUI:
        self._char_map = char_map
        self._art_builder = AsciiArtBuilder(self._renderer, char_map)
        return self

    def set_border_style(self, style: BorderStyle) -> ConsoleUI:
        self._border_style = style
        self._box_builder = BoxBuilder(
            self._renderer, border_style=style,
        )
        self._panel_builder = PanelBuilder(
            self._renderer, self._console, style, self._normal_mode,
        )
        return self

    def refresh_size(self) -> ConsoleUI:
        self._renderer.update_reference_width()
        return self

    def reset_lines(self) -> ConsoleUI:
        self._line_count = 0
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 核心输出方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

