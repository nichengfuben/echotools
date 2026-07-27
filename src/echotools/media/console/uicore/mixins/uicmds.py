"""ConsoleUI mixins."""
from __future__ import annotations

import asyncio
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Sequence,
    Set,
)

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_types import (
    ANSI_RESET,
    RGB,
)


class _ConsoleUICmdsMixin:
    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        aliases: Optional[Sequence[str]] = None,
    ) -> ConsoleUI:
        """注册命令"""
        cmd_info = {
            "func": func,
            "description": description,
            "aliases": list(aliases) if aliases else [],
        }
        self._commands[name] = cmd_info
        if aliases:
            for alias in aliases:
                self._commands[alias] = cmd_info
        return self

    def unregister(self, name: str) -> ConsoleUI:
        """注销命令"""
        cmd = self._commands.pop(name, None)
        if cmd and cmd.get("aliases"):
            for alias in cmd["aliases"]:
                self._commands.pop(alias, None)
        return self

    async def execute(self, name: str, *args: Any, **kwargs: Any) -> bool:
        """执行命令"""
        if name not in self._commands:
            return False
        func = self._commands[name]["func"]
        try:
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)
            return True
        except Exception as e:
            self.error(f"Command '{name}' failed: {e}")
            return False

    def show_commands(self) -> ConsoleUI:
        """显示所有命令"""
        seen: Set[int] = set()
        items: Dict[str, str] = {}
        for name, cmd_info in self._commands.items():
            cmd_id = id(cmd_info)
            if cmd_id in seen:
                continue
            seen.add(cmd_id)
            desc = cmd_info.get("description", "No description")
            aliases = cmd_info.get("aliases", [])
            if aliases:
                desc += f" (aliases: {', '.join(aliases)})"
            items[name] = desc
        self.kv_list(items)
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 便捷组合方法
    # ══════════════════════════════════════════════════════════════════════════

    def header(self, title: str, subtitle: str = "") -> ConsoleUI:
        """打印应用头部（标题 + 分隔线 + 可选副标题）"""
        self.color(title)
        if subtitle:
            if self._normal_mode:
                print(subtitle)
            else:
                mr, mg, mb = self._renderer.theme.muted
                _write_flush(
                    f"\033[38;2;{mr};{mg};{mb}m{subtitle}{ANSI_RESET}\n",
                )
            self._line_count += 1
        self.divider()
        return self

    def section(self, title: str) -> ConsoleUI:
        """打印章节标题"""
        return self.newline().divider(title=title).newline()

    def bullet_list(
        self, items: Sequence[str], bullet: str = " *",
    ) -> ConsoleUI:
        """打印项目符号列表"""
        for item in items:
            if self._normal_mode:
                print(f"{bullet} {item}")
            else:
                r, g, b = self._renderer.theme.accent_start
                bullet_ansi = f"\033[38;2;{r};{g};{b}m{bullet}{ANSI_RESET}"
                item_ansi = self._renderer.render_text_ansi(item)
                _write_flush(f"{bullet_ansi} {item_ansi}\n")
            self._line_count += 1
        return self

    def numbered_list(self, items: Sequence[str]) -> ConsoleUI:
        """打印编号列表"""
        width = len(str(len(items)))
        for i, item in enumerate(items, 1):
            num = f"{i:>{width}}."
            if self._normal_mode:
                print(f" {num} {item}")
            else:
                r, g, b = self._renderer.theme.accent_start
                num_ansi = f"\033[38;2;{r};{g};{b}m {num}{ANSI_RESET}"
                item_ansi = self._renderer.render_text_ansi(item)
                _write_flush(f"{num_ansi} {item_ansi}\n")
            self._line_count += 1
        return self

    def quote(self, text: str) -> ConsoleUI:
        """打印引用块"""
        for line in text.splitlines():
            if self._normal_mode:
                print(f" | {line}")
            else:
                mr, mg, mb = self._renderer.theme.muted
                bar = f"\033[38;2;{mr};{mg};{mb}m |{ANSI_RESET}"
                line_ansi = self._renderer.render_text_ansi(f" {line}")
                _write_flush(f"{bar}{line_ansi}\n")
            self._line_count += 1
        return self

    def badge(self, text: str, color: Optional[RGB] = None) -> ConsoleUI:
        """打印徽章标签"""
        r, g, b = color or self._renderer.theme.primary_start
        if self._normal_mode:
            print(f"[{text}]")
        else:
            _write_flush(
                f"\033[48;2;{r};{g};{b}m"
                f"\033[38;2;255;255;255m {text} {ANSI_RESET}\n",
            )
        self._line_count += 1
        return self

    def pairs(self, label: str, value: str) -> ConsoleUI:
        """打印单个键值对"""
        if self._normal_mode:
            print(f"{label}: {value}")
        else:
            label_ansi = self._renderer.render_text_ansi(
                label, is_border=True,
            )
            mr, mg, mb = self._renderer.theme.muted
            sep = f"\033[38;2;{mr};{mg};{mb}m: {ANSI_RESET}"
            val_ansi = self._renderer.render_text_ansi(value)
            _write_flush(f"{label_ansi}{sep}{val_ansi}\n")
        self._line_count += 1
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # REPL 循环
    # ══════════════════════════════════════════════════════════════════════════

    async def repl(
        self,
        prompt: str = "> ",
        exit_commands: Optional[Set[str]] = None,
        handler: Optional[Callable[[str], Awaitable[Optional[bool]]]] = None,
    ) -> ConsoleUI:
        """
        异步 REPL 循环

        参数：
          prompt: 提示符
          exit_commands: 退出命令集合（默认 {"exit", "quit", "q"}）
          handler: 输入处理函数，返回 False 时退出循环
        """
        exits = exit_commands or {"exit", "quit", "q"}

        while True:
            try:
                line = await self.input_async(prompt)
                stripped = line.strip()

                if stripped.lower() in exits:
                    break

                if stripped in self._commands:
                    await self.execute(stripped)
                    continue

                if handler is not None:
                    result = await handler(stripped)
                    if result is False:
                        break

            except KeyboardInterrupt:
                self.newline()
                break
            except EOFError:
                break

        return self

