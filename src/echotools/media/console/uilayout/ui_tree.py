"""Column layout and tree view components."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from rich.console import Console

from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils


class ColumnLayout:
    """多列布局 - 将文本排列为多列"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
        gap: int = 2,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode
        self.gap = gap

    def render(
        self,
        columns: Sequence[Sequence[str]],
        col_widths: Optional[Sequence[int]] = None,
        row_offset: int = 0,
    ) -> int:
        """渲染多列布局，返回行数"""
        if not columns:
            return 0

        num_cols = len(columns)
        max_rows = max(len(col) for col in columns)

        if col_widths is None:
            widths = [
                max(
                    (TextUtils.display_width(line) for line in col),
                    default=0,
                )
                for col in columns
            ]
        else:
            widths = list(col_widths)

        gap_str = " " * self.gap
        lines_rendered = 0

        for row_idx in range(max_rows):
            parts: List[str] = []
            for col_idx, col in enumerate(columns):
                cell = col[row_idx] if row_idx < len(col) else ""
                padded = TextUtils.pad_to_width(cell, widths[col_idx])
                if col_idx < num_cols - 1:
                    padded += gap_str
                parts.append(padded)

            line_text = "".join(parts)
            if self.normal_mode:
                print(line_text)
            else:
                self.console.print(
                    self.renderer.render_line(
                        line_text, row=row_offset + row_idx,
                    ),
                )
            lines_rendered += 1

        return lines_rendered


@dataclass
class TreeNode:
    """树节点"""
    label: str
    children: List[TreeNode] = field(default_factory=list)

    def add_child(self, label: str) -> TreeNode:
        """添加子节点并返回子节点"""
        child = TreeNode(label=label)
        self.children.append(child)
        return child


class TreeView:
    """树形视图渲染器"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode

    def render(self, root: TreeNode, row_offset: int = 0) -> int:
        """渲染树形视图，返回行数"""
        lines = self._build_lines(root, prefix="", is_last=True, is_root=True)
        for idx, line in enumerate(lines):
            if self.normal_mode:
                print(line)
            else:
                self.console.print(
                    self.renderer.render_line(
                        line, row=row_offset + idx,
                    ),
                )
        return len(lines)

    def _build_lines(
        self,
        node: TreeNode,
        prefix: str,
        is_last: bool,
        is_root: bool,
    ) -> List[str]:
        """递归构建树形行"""
        lines: List[str] = []

        if is_root:
            lines.append(node.label)
            child_prefix = ""
        else:
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{node.label}")
            child_prefix = prefix + ("    " if is_last else "│   ")

        for i, child in enumerate(node.children):
            child_is_last = i == len(node.children) - 1
            lines.extend(
                self._build_lines(
                    child,
                    prefix=child_prefix,
                    is_last=child_is_last,
                    is_root=False,
                ),
            )

        return lines
