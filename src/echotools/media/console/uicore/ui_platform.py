"""Platform backends for console key input."""
from __future__ import annotations

import os
import sys
from typing import Final, List, Optional, Protocol

from echotools.media.console.uicore.ui_types import IS_WINDOWS

# ══════════════════════════════════════════════════════════════════════════════
# 平台抽象层
# ══════════════════════════════════════════════════════════════════════════════


class _PlatformBackend(Protocol):
    """平台后端协议 - 抽象不同操作系统的控制台交互"""

    def init_console(self) -> None:
        """初始化控制台（启用 ANSI 等）"""
        ...

    def read_key_events(self) -> List[dict]:
        """
        读取按键事件，返回标准化事件字典列表。

        每个字典包含：
          - "type": "key"
          - "vk": 虚拟键码（整数）或特殊名称字符串
          - "char": 字符（str）或空字符串
          - "ctrl": 是否按下 Ctrl
        """
        ...

    def getch(self) -> str:
        """阻塞读取单个字符（用于分页器等简单场景）"""
        ...


class _WindowsBackend:
    """Windows 控制台后端"""

    VK_RETURN: Final[int] = 0x0D
    VK_BACK: Final[int] = 0x08
    VK_ESCAPE: Final[int] = 0x1B
    VK_LEFT: Final[int] = 0x25
    VK_RIGHT: Final[int] = 0x27
    VK_UP: Final[int] = 0x26
    VK_DOWN: Final[int] = 0x28
    VK_DELETE: Final[int] = 0x2E
    VK_HOME: Final[int] = 0x24
    VK_END: Final[int] = 0x23
    VK_TAB: Final[int] = 0x09
    KEY_EVENT: Final[int] = 0x0001

    def __init__(self) -> None:
        import ctypes
        import ctypes.wintypes

        self._ctypes = ctypes
        self._kernel32 = ctypes.windll.kernel32
        self._stdin_handle = self._kernel32.GetStdHandle(
            ctypes.wintypes.DWORD(-10),
        )
        self._define_structures()

    def _define_structures(self) -> None:
        """定义 Windows 控制台输入记录结构体"""
        ct = self._ctypes

        class COORD(ct.Structure):
            _fields_ = [("X", ct.c_short), ("Y", ct.c_short)]

        class KEY_EVENT_RECORD(ct.Structure):
            _fields_ = [
                ("bKeyDown", ct.wintypes.BOOL),
                ("wRepeatCount", ct.wintypes.WORD),
                ("wVirtualKeyCode", ct.wintypes.WORD),
                ("wVirtualScanCode", ct.wintypes.WORD),
                ("uChar", ct.wintypes.WCHAR),
                ("dwControlKeyState", ct.wintypes.DWORD),
            ]

        class MOUSE_EVENT_RECORD(ct.Structure):
            _fields_ = [
                ("dwMousePosition", COORD),
                ("dwButtonState", ct.wintypes.DWORD),
                ("dwControlKeyState", ct.wintypes.DWORD),
                ("dwEventFlags", ct.wintypes.DWORD),
            ]

        class WINDOW_BUFFER_SIZE_RECORD(ct.Structure):
            _fields_ = [("dwSize", COORD)]

        class MENU_EVENT_RECORD(ct.Structure):
            _fields_ = [("dwCommandId", ct.wintypes.UINT)]

        class FOCUS_EVENT_RECORD(ct.Structure):
            _fields_ = [("bSetFocus", ct.wintypes.BOOL)]

        class INPUT_RECORD_EVENT(ct.Union):
            _fields_ = [
                ("KeyEvent", KEY_EVENT_RECORD),
                ("MouseEvent", MOUSE_EVENT_RECORD),
                ("WindowBufferSizeEvent", WINDOW_BUFFER_SIZE_RECORD),
                ("MenuEvent", MENU_EVENT_RECORD),
                ("FocusEvent", FOCUS_EVENT_RECORD),
            ]

        class INPUT_RECORD(ct.Structure):
            _fields_ = [
                ("EventType", ct.wintypes.WORD),
                ("Event", INPUT_RECORD_EVENT),
            ]

        self._INPUT_RECORD = INPUT_RECORD

    def init_console(self) -> None:
        """启用 Windows 控制台 ANSI 支持，并将 Ctrl+C 改为 KEY_EVENT"""
        ctypes = self._ctypes
        stdout_handle = self._kernel32.GetStdHandle(
            ctypes.wintypes.DWORD(-11),
        )
        mode = ctypes.wintypes.DWORD()
        self._kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
        self._kernel32.SetConsoleMode(
            stdout_handle, mode.value | 0x0004 | 0x0001,
        )
        stdin_mode = ctypes.wintypes.DWORD()
        self._kernel32.GetConsoleMode(
            self._stdin_handle, ctypes.byref(stdin_mode),
        )
        self._kernel32.SetConsoleMode(
            self._stdin_handle, stdin_mode.value & ~0x0001,
        )

    def read_key_events(self) -> List[dict]:
        """通过 ReadConsoleInputW 读取按键事件"""
        ctypes = self._ctypes
        results: List[dict] = []

        wait_result = self._kernel32.WaitForSingleObject(
            self._stdin_handle, ctypes.wintypes.DWORD(100),
        )
        if wait_result != 0:
            return results

        num_events = ctypes.wintypes.DWORD(0)
        self._kernel32.GetNumberOfConsoleInputEvents(
            self._stdin_handle, ctypes.byref(num_events),
        )
        if num_events.value == 0:
            return results

        buf = (self._INPUT_RECORD * num_events.value)()
        events_read = ctypes.wintypes.DWORD(0)
        self._kernel32.ReadConsoleInputW(
            self._stdin_handle, buf, num_events.value,
            ctypes.byref(events_read),
        )

        for i in range(events_read.value):
            record = buf[i]
            if record.EventType != self.KEY_EVENT:
                continue
            key_event = record.Event.KeyEvent
            if not key_event.bKeyDown:
                continue
            ctrl_state = key_event.dwControlKeyState
            ctrl = bool(ctrl_state & 0x0008) or bool(ctrl_state & 0x0004)
            results.append({
                "type": "key",
                "vk": key_event.wVirtualKeyCode,
                "char": key_event.uChar or "",
                "ctrl": ctrl,
            })

        return results

    def getch(self) -> str:
        """Windows 下阻塞读取单个字符"""
        import msvcrt
        return msvcrt.getwch()


def _unix_key_event(vk: str, char: str = "", ctrl: bool = False) -> dict:
    return {"type": "key", "vk": vk, "char": char, "ctrl": ctrl}


def _unix_parse_escape(fd: int, select_mod) -> dict:
    """Parse ANSI escape sequence after leading ESC."""
    more, _, _ = select_mod.select([fd], [], [], 0.05)
    if not more:
        return _unix_key_event("escape")
    ch2 = os.read(fd, 1).decode("utf-8", errors="replace")
    if ch2 != "[":
        return _unix_key_event("escape")
    ch3 = os.read(fd, 1).decode("utf-8", errors="replace")
    arrow_map = {
        "A": "up", "B": "down", "C": "right", "D": "left",
        "H": "home", "F": "end", "3": "delete",
    }
    vk = arrow_map.get(ch3, "unknown")
    if ch3 == "3":
        pending_del, _, _ = select_mod.select([fd], [], [], 0.02)
        if pending_del:
            os.read(fd, 1)
    return _unix_key_event(vk)


def _unix_control_map() -> dict[str, tuple[str, str, bool]]:
    return {
        "\r": ("return", "\r", False),
        "\n": ("return", "\r", False),
        "\x7f": ("backspace", "", False),
        "\x08": ("backspace", "", False),
        "\x03": ("interrupt", "", True),
        "\x04": ("eof", "", True),
        "\x01": ("home", "", True),
        "\x05": ("end", "", True),
        "\x15": ("clear_line", "", True),
        "\x0b": ("kill_to_end", "", True),
        "\x17": ("delete_word", "", True),
        "\t": ("tab", "\t", False),
    }


def _unix_read_utf8_char(fd: int, select_mod, ch: str) -> str:
    full_char = ch
    if ord(ch) <= 127:
        return full_char
    more, _, _ = select_mod.select([fd], [], [], 0.02)
    if more:
        utf_tail = os.read(fd, 3).decode("utf-8", errors="replace")
        full_char += utf_tail
    return full_char


def _unix_key_from_char(ch: str, fd: int, select_mod) -> dict:
    ctrl_map = _unix_control_map()
    if ch in ctrl_map:
        vk, char, ctrl = ctrl_map[ch]
        return _unix_key_event(vk, char, ctrl)
    if ord(ch) >= 32:
        full_char = _unix_read_utf8_char(fd, select_mod, ch)
        return _unix_key_event("char", full_char, False)
    return _unix_key_event(f"ctrl_{ord(ch)}", ch, True)


class _UnixBackend:
    """Unix (Linux / macOS) 控制台后端"""

    def __init__(self) -> None:
        self._old_settings: Optional[list] = None

    def init_console(self) -> None:
        """Unix 下无需特殊初始化"""

    def read_key_events(self) -> List[dict]:
        """Unix 下读取按键事件（termios raw 模式）"""
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        results: List[dict] = []

        try:
            tty.setraw(fd)
            readable, _, _ = select.select([fd], [], [], 0.1)
            if not readable:
                return results

            ch = os.read(fd, 1).decode("utf-8", errors="replace")
            if ch == "\x1b":
                results.append(_unix_parse_escape(fd, select))
            else:
                results.append(_unix_key_from_char(ch, fd, select))
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return results

    def getch(self) -> str:
        """Unix 下阻塞读取单个字符"""
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                more, _, _ = select.select([fd], [], [], 0.05)
                if more:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        sys.stdin.read(1)
                return "\x1b"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _create_backend() -> _PlatformBackend:
    """根据平台创建对应的控制台后端"""
    if IS_WINDOWS:
        try:
            backend = _WindowsBackend()
            backend.init_console()
            return backend
        except Exception:
            pass
    return _UnixBackend()


_backend: Optional[_PlatformBackend] = None


def _get_backend() -> _PlatformBackend:
    """获取全局平台后端实例"""
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend


# ══════════════════════════════════════════════════════════════════════════════
# 按键事件标准化
# ══════════════════════════════════════════════════════════════════════════════

_WIN_VK_MAP = {
    0x0D: "return",
    0x08: "backspace",
    0x1B: "escape",
    0x25: "left",
    0x27: "right",
    0x26: "up",
    0x28: "down",
    0x2E: "delete",
    0x24: "home",
    0x23: "end",
    0x09: "tab",
}

_WIN_CTRL_MAP = {
    0x43: "interrupt",
    0x44: "eof",
    0x55: "clear_line",
    0x41: "home",
    0x45: "end",
    0x57: "delete_word",
    0x4B: "kill_to_end",
}


def _normalize_windows_key(vk: int, char: str, ctrl: bool) -> dict:
    if vk in _WIN_VK_MAP:
        return {"type": "key", "vk": _WIN_VK_MAP[vk], "char": char, "ctrl": ctrl}
    if ctrl and vk in _WIN_CTRL_MAP:
        return {
            "type": "key",
            "vk": _WIN_CTRL_MAP[vk],
            "char": char,
            "ctrl": True,
        }
    if char and ord(char) >= 32:
        return {"type": "key", "vk": "char", "char": char, "ctrl": False}
    return {"type": "key", "vk": vk, "char": char, "ctrl": ctrl}


def _normalize_key_event(event: dict) -> dict:
    """
    将平台特定的按键事件标准化为统一格式。

    统一后的 vk 值：
      "return", "backspace", "delete", "left", "right", "up", "down",
      "home", "end", "escape", "tab", "interrupt",
      "clear_line", "kill_to_end", "delete_word", "char"
    """
    if not IS_WINDOWS:
        return event

    vk = event.get("vk", 0)
    ctrl = event.get("ctrl", False)
    char = event.get("char", "")
    return _normalize_windows_key(vk, char, ctrl)
