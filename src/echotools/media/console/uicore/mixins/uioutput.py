"""ConsoleUI mixins."""
from __future__ import annotations

import sys
from typing import (
    TYPE_CHECKING,
    Mapping,
    Optional,
    Sequence,
)

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

from echotools.media.console.uicore.ui_types import (
    BorderStyle,
    FontStyle,
)
from echotools.media.console.uilayout.ui_panel import PanelBuilder
from echotools.media.console.uilayout.ui_table import TableBuilder
from echotools.media.console.uilayout.ui_tree import TreeNode
from echotools.media.console.uiwidgets.ui_box import BoxBuilder


class _ConsoleUIOutputMixin:
    def print(
        self,
        text: str = "",
        style: FontStyle = FontStyle.NORMAL,
        prefix: str = "",
        newline: bool = True,
    ) -> ConsoleUI:
        """通用打印方法"""
        if not text:
            print()
            self._line_count += 1
            return self

        if self._normal_mode:
            print(text, end="\n" if newline else "")
            self._line_count += text.count("\n") + (1 if newline else 0)
            self._log_writer.write(text)
            return self

        if style == FontStyle.NORMAL:
            print(text, end="\n" if newline else "")
            self._line_count += text.count("\n") + (1 if newline else 0)

        elif style == FontStyle.COLOR:
            rendered = self._renderer.render_banner(
                text, row_offset=self._line_count,
            )
            self._console.print(rendered, end="\n" if newline else "")
            self._line_count += text.count("\n") + (1 if newline else 0)

        elif style == FontStyle.ART:
            rendered, art_line_count = self._art_builder.build(
                text, row_offset=self._line_count,
            )
            self._console.print(rendered)
            self._line_count += art_line_count

        elif style == FontStyle.BOX:
            box_lines = self._box_builder.build(
                text, prefix, self._line_count,
            )
            for line in box_lines:
                self._console.print(line)
            self._line_count += len(box_lines)

        self._log_writer.write(text)
        return self

    def text(self, content: str, newline: bool = True) -> ConsoleUI:
        """打印普通文本"""
        return self.print(content, FontStyle.NORMAL, newline=newline)

    def color(self, content: str, newline: bool = True) -> ConsoleUI:
        """打印彩色渐变文本"""
        return self.print(content, FontStyle.COLOR, newline=newline)

    def art(self, content: str) -> ConsoleUI:
        """打印 ASCII 艺术字"""
        return self.print(content, FontStyle.ART)

    def box(
        self,
        content: str,
        prefix: str = "",
        title: str = "",
        border_style: Optional[BorderStyle] = None,
    ) -> ConsoleUI:
        """打印文本盒子"""
        builder = (
            BoxBuilder(self._renderer, border_style=border_style)
            if border_style is not None
            else self._box_builder
        )
        box_lines = builder.build(
            content, prefix, self._line_count, title=title,
        )
        for line in box_lines:
            self._console.print(line)
        self._line_count += len(box_lines)
        self._log_writer.write(content)
        return self

    def newline(self, count: int = 1) -> ConsoleUI:
        """打印空行"""
        for _ in range(count):
            print()
        self._line_count += count
        return self

    def banner(self, text: str, use_border: bool = True) -> ConsoleUI:
        """打印渐变横幅"""
        if self._normal_mode:
            print(text)
        else:
            rendered = self._renderer.render_banner(
                text,
                use_border_colors=use_border,
                row_offset=self._line_count,
            )
            self._console.print(rendered)
        self._line_count += text.count("\n") + 1
        self._log_writer.write(text)
        return self

    def raw(self, ansi_text: str, newline: bool = True) -> ConsoleUI:
        """直接输出 ANSI 文本"""
        sys.stdout.write(ansi_text)
        if newline:
            sys.stdout.write("\n")
        sys.stdout.flush()
        self._line_count += ansi_text.count("\n") + (1 if newline else 0)
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 通知快捷方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def success(self, message: str) -> ConsoleUI:
        """成功通知"""
        self._notification.show(message, "success")
        self._line_count += 1
        self._log_writer.write(f"[SUCCESS] {message}")
        return self

    def warning(self, message: str) -> ConsoleUI:
        """警告通知"""
        self._notification.show(message, "warning")
        self._line_count += 1
        self._log_writer.write(f"[WARNING] {message}")
        return self

    def error(self, message: str) -> ConsoleUI:
        """错误通知"""
        self._notification.show(message, "error")
        self._line_count += 1
        self._log_writer.write(f"[ERROR] {message}")
        return self

    def info(self, message: str) -> ConsoleUI:
        """信息通知"""
        self._notification.show(message, "info")
        self._line_count += 1
        self._log_writer.write(f"[INFO] {message}")
        return self

    def debug(self, message: str) -> ConsoleUI:
        """调试通知"""
        self._notification.show(message, "debug")
        self._line_count += 1
        self._log_writer.write(f"[DEBUG] {message}")
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 分隔线（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def divider(
        self,
        char: str = "─",
        title: str = "",
        width: Optional[int] = None,
    ) -> ConsoleUI:
        """打印分隔线"""
        self._divider.render(
            char=char, title=title, width=width, row=self._line_count,
        )
        self._line_count += 1
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 面板（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def panel(
        self,
        content: str,
        title: str = "",
        subtitle: str = "",
        width: Optional[int] = None,
        border_style: Optional[BorderStyle] = None,
    ) -> ConsoleUI:
        """打印面板"""
        builder = (
            PanelBuilder(
                self._renderer, self._console,
                border_style, self._normal_mode,
            )
            if border_style is not None
            else self._panel_builder
        )
        lines = builder.render(
            content,
            title=title,
            subtitle=subtitle,
            width=width,
            row_offset=self._line_count,
        )
        self._line_count += lines
        self._log_writer.write(content)
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 表格
    # ══════════════════════════════════════════════════════════════════════════

    def table(
        self,
        headers: Optional[Sequence[str]] = None,
        border_style: Optional[BorderStyle] = None,
    ) -> TableBuilder:
        """创建表格构建器"""
        return TableBuilder(
            self._renderer,
            self._console,
            headers=headers,
            border_style=border_style or self._border_style,
            normal_mode=self._normal_mode,
        )

    def print_table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        border_style: Optional[BorderStyle] = None,
    ) -> ConsoleUI:
        """直接打印表格"""
        tb = self.table(headers, border_style)
        tb.add_rows(rows)
        lines = tb.render(row_offset=self._line_count)
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 键值对列表（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def kv_list(
        self,
        items: Mapping[str, str],
        separator: str = " : ",
    ) -> ConsoleUI:
        """打印键值对列表"""
        self._kv_list.separator = separator
        lines = self._kv_list.render(items)
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 列布局（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def columns(
        self,
        cols: Sequence[Sequence[str]],
        col_widths: Optional[Sequence[int]] = None,
        gap: int = 2,
    ) -> ConsoleUI:
        """打印多列布局"""
        self._column_layout.gap = gap
        lines = self._column_layout.render(
            cols, col_widths, row_offset=self._line_count,
        )
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 树形视图（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def tree(self, root: TreeNode) -> ConsoleUI:
        """打印树形视图"""
        lines = self._tree_view.render(root, row_offset=self._line_count)
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 流式输出方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

