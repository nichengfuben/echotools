"""Line editor and async input."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from rich.console import Console

from echotools.media.console.uicore.ui_io import _write_flush
from echotools.media.console.uicore.ui_platform import (
    _get_backend,
    _normalize_key_event,
)
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import (
    ANSI_CLEAR_LINE,
    ANSI_HIDE_CURSOR,
    ANSI_RESET,
    ANSI_SHOW_CURSOR,
)


@dataclass
class _LineEditorState:
    """行编辑器状态"""
    buffer: List[str] = field(default_factory=list)
    cursor_pos: int = 0
    history_index: int = -1
    saved_input: str = ""


class _LineEditor:
    """
    行编辑器 - 封装编辑逻辑，与平台无关。

    将标准化后的按键事件转换为对缓冲区的操作。
    """

    @staticmethod
    def _process_history_key(
        vk: str, state: _LineEditorState, history: List[str],
    ) -> bool:
        if vk == "up" and history:
            if state.history_index == -1:
                state.saved_input = "".join(state.buffer)
                state.history_index = len(history) - 1
            elif state.history_index > 0:
                state.history_index -= 1
            else:
                return True
            state.buffer = list(history[state.history_index])
            state.cursor_pos = len(state.buffer)
            return True
        if vk == "down" and state.history_index >= 0:
            if state.history_index < len(history) - 1:
                state.history_index += 1
                state.buffer = list(history[state.history_index])
            else:
                state.history_index = -1
                state.buffer = list(state.saved_input)
                state.saved_input = ""
            state.cursor_pos = len(state.buffer)
            return True
        return False

    @staticmethod
    def _process_edit_key(vk: str, state: _LineEditorState) -> bool:
        buf = state.buffer
        pos = state.cursor_pos
        if vk == "clear_line":
            state.buffer = []
            state.cursor_pos = 0
            return True
        if vk == "home":
            state.cursor_pos = 0
            return True
        if vk == "end":
            state.cursor_pos = len(buf)
            return True
        if vk == "kill_to_end":
            state.buffer = list(buf[:pos])
            return True
        if vk == "delete_word":
            new_buf = list(buf)
            new_pos = pos
            while new_pos > 0 and new_buf[new_pos - 1] == " ":
                new_buf.pop(new_pos - 1)
                new_pos -= 1
            while new_pos > 0 and new_buf[new_pos - 1] != " ":
                new_buf.pop(new_pos - 1)
                new_pos -= 1
            state.buffer = new_buf
            state.cursor_pos = new_pos
            return True
        if vk == "backspace" and pos > 0:
            buf.pop(pos - 1)
            state.cursor_pos = pos - 1
            return True
        if vk == "delete" and pos < len(buf):
            buf.pop(pos)
            return True
        if vk == "left" and pos > 0:
            state.cursor_pos = pos - 1
            return True
        if vk == "right" and pos < len(buf):
            state.cursor_pos = pos + 1
            return True
        return False

    @staticmethod
    def process_event(
        event: dict,
        state: _LineEditorState,
        history: List[str],
    ) -> Optional[str]:
        """
        处理按键事件并更新状态。

        返回值：
          - None: 无终端操作，继续编辑
          - 字符串: 完成输入，返回最终文本
        
        特殊情况抛出 KeyboardInterrupt。
        """
        vk = event.get("vk", "")
        char = event.get("char", "")

        if vk == "return":
            return "".join(state.buffer)

        if vk == "interrupt":
            raise KeyboardInterrupt

        if vk == "eof":
            raise EOFError

        if _LineEditor._process_edit_key(vk, state):
            return None

        if vk in ("up", "down") and _LineEditor._process_history_key(vk, state, history):
            return None

        if vk == "escape":
            state.buffer = []
            state.cursor_pos = 0
            state.history_index = -1
            state.saved_input = ""
            return None

        if vk == "tab":
            return None

        # 可打印字符
        if vk == "char" and char:
            for c in char:
                state.buffer.insert(state.cursor_pos, c)
                state.cursor_pos += 1
            return None

        return None


# ══════════════════════════════════════════════════════════════════════════════
# 异步输入处理器
# ══════════════════════════════════════════════════════════════════════════════


def _longest_common_prefix(strings: List[str]) -> str:
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def _tab_complete(
    current: str,
    completer: Callable[[str], List[str]],
    state: _LineEditorState,
) -> None:
    """补全当前输入。多候选时取第一个（排序最靠前的命令）。"""
    candidates = completer(current)
    if not candidates:
        return
    completed = candidates[0] if len(candidates) == 1 else _longest_common_prefix(candidates)
    if not completed or completed == current:
        # 前缀无法前进时直接取第一个候选
        completed = candidates[0]
    state.buffer = list(completed)
    state.cursor_pos = len(state.buffer)


class AsyncInput:
    """
    异步输入处理器

    核心设计：
    1. 通过平台后端 (_PlatformBackend) 读取原始按键事件
    2. 事件标准化后统一交给 _LineEditor 处理
    3. 完全兼容 Windows IME 中文输入法
    4. 支持光标移动、Home/End、Delete 等编辑操作
    5. 支持输入历史
    """

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
        completer: Callable[[str], List[str]] | None = None,
        history_path: Path | None = None,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode
        self._completer = completer
        self._history_path = history_path
        self._last_drawn: str = ""
        self._history: List[str] = []
        self._max_history: int = 500
        if history_path is not None:
            self._load_history()

    def _load_history(self) -> None:
        try:
            if self._history_path and self._history_path.exists():
                raw = self._history_path.read_text(encoding="utf-8").splitlines()
                seen: set = set()
                deduped: List[str] = []
                for line in reversed(raw):
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
                        deduped.append(line)
                self._history = list(reversed(deduped))[-self._max_history:]
        except Exception:
            pass

    def add_history(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        if self._history and self._history[-1] == line:
            return
        self._history.append(line)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        if self._history_path is not None:
            try:
                self._history_path.parent.mkdir(parents=True, exist_ok=True)
                with self._history_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    async def readline(self, prompt: str = "> ") -> str:
        """异步读取一行输入"""
        if self.normal_mode:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: input(prompt))
        else:
            result = await self._interactive_readline(prompt)
        self.add_history(result)
        return result

    async def _poll_events(
        self,
        backend: Any,
        state: _LineEditorState,
        prompt: str,
        loop: asyncio.AbstractEventLoop,
    ) -> str:
        while True:
            raw_events = await loop.run_in_executor(None, backend.read_key_events)
            if not raw_events:
                await asyncio.sleep(0.01)
                continue
            dirty = False
            for raw in raw_events:
                event = _normalize_key_event(raw)
                if event.get("vk") == "tab" and self._completer is not None:
                    current = "".join(state.buffer)
                    if current:
                        _tab_complete(current, self._completer, state)
                    dirty = True
                    continue
                result = _LineEditor.process_event(event, state, self._history)
                if result is not None:
                    self._finish_line()
                    return result
                dirty = True
            if dirty:
                self._draw_with_ghost(prompt, state)

    def _draw_with_ghost(self, prompt: str, state: _LineEditorState) -> None:
        buf = "".join(state.buffer)
        ghost = ""
        if self._completer and buf:
            cands = self._completer(buf)
            if cands:
                lcp = cands[0] if len(cands) == 1 else _longest_common_prefix(cands)
                if lcp.startswith(buf):
                    ghost = lcp[len(buf):]
        self._draw_line(prompt, state, ghost=ghost)

    async def _interactive_readline(self, prompt: str) -> str:
        """通过平台后端交互式读取输入"""
        backend = _get_backend()
        state = _LineEditorState()
        self._last_drawn = ""
        self._draw_line(prompt, state)
        loop = asyncio.get_running_loop()
        try:
            return await self._poll_events(backend, state, prompt, loop)
        except BaseException:
            self._draw_line(prompt, state, ghost="")
            self._finish_line()
            raise

    def _draw_line(
        self,
        prompt: str,
        state: _LineEditorState,
        ghost: str = "",
    ) -> None:
        """绘制整行（提示符 + 输入内容 + ghost text）"""
        buffer_str = "".join(state.buffer)
        full_text = prompt + buffer_str

        cache_key = f"{full_text}|{state.cursor_pos}|{ghost}"
        if cache_key == self._last_drawn:
            return
        self._last_drawn = cache_key

        line_content = self.renderer.render_text_ansi(full_text)
        ghost_part = f"\033[2m{ghost}\033[0m" if ghost else ""

        prompt_dw = TextUtils.display_width(prompt)
        before_cursor = "".join(state.buffer[:state.cursor_pos])
        cursor_col = prompt_dw + TextUtils.display_width(before_cursor)

        _write_flush(
            f"{ANSI_HIDE_CURSOR}"
            f"{ANSI_CLEAR_LINE}"
            f"{line_content}{ghost_part}"
            f"\r\033[{cursor_col}C"
            f"{ANSI_SHOW_CURSOR}",
        )

    @staticmethod
    def _finish_line() -> None:
        """完成当前行的输入"""
        _write_flush(f"{ANSI_SHOW_CURSOR}{ANSI_RESET}\n")

