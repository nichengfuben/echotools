"""
ConsoleUI - 高性能异步控制台UI框架

支持渐变文本、边框、ASCII艺术字、流式输出、交互式选择、
进度条、Spinner、表格、面板、分隔线、确认对话框、计时器、分页等功能。

极致便携，支持调用链，完整解决中文输入法兼容问题。

设计原则：
  - 调用链优先：所有输出方法返回 self
  - 异步优先：核心 I/O 均提供 async 版本
  - 零依赖可选：仅 rich / wcwidth 为必选依赖
  - IME 兼容：Windows 下通过 ReadConsoleInput 正确处理中文输入法
  - 全平台适配：Windows / Linux / macOS 均可无缝运行
"""

from __future__ import annotations

import asyncio
import datetime
import math
import os
import re
import sys
from pathlib import Path
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    ClassVar,
    Dict,
    Final,
    Iterator,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    runtime_checkable,
)

from rich.console import Console
from rich.text import Text
from wcwidth import wcwidth, wcswidth

# ══════════════════════════════════════════════════════════════════════════════
# 类型定义与平台常量
# ══════════════════════════════════════════════════════════════════════════════

RGB = Tuple[int, int, int]
T = TypeVar("T")
IS_WINDOWS: Final[bool] = sys.platform == "win32"
IS_MACOS: Final[bool] = sys.platform == "darwin"
IS_LINUX: Final[bool] = sys.platform.startswith("linux")

# ANSI 转义序列常量
ANSI_RESET: Final[str] = "\033[0m"
ANSI_HIDE_CURSOR: Final[str] = "\033[?25l"
ANSI_SHOW_CURSOR: Final[str] = "\033[?25h"
ANSI_CLEAR_LINE: Final[str] = "\r\033[K"
ANSI_MOVE_UP: Final[str] = "\033[F"
ANSI_CLEAR_SCREEN: Final[str] = "\033[2J\033[H"
ANSI_BOLD: Final[str] = "\033[1m"

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

    # 虚拟键码常量
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

        # 定义 INPUT_RECORD 结构体
        self._define_structures()

    def _define_structures(self) -> None:
        """定义 Windows 控制台输入记录结构体"""
        ctypes = self._ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class KEY_EVENT_RECORD(ctypes.Structure):
            _fields_ = [
                ("bKeyDown", ctypes.wintypes.BOOL),
                ("wRepeatCount", ctypes.wintypes.WORD),
                ("wVirtualKeyCode", ctypes.wintypes.WORD),
                ("wVirtualScanCode", ctypes.wintypes.WORD),
                ("uChar", ctypes.wintypes.WCHAR),
                ("dwControlKeyState", ctypes.wintypes.DWORD),
            ]

        class MOUSE_EVENT_RECORD(ctypes.Structure):
            _fields_ = [
                ("dwMousePosition", COORD),
                ("dwButtonState", ctypes.wintypes.DWORD),
                ("dwControlKeyState", ctypes.wintypes.DWORD),
                ("dwEventFlags", ctypes.wintypes.DWORD),
            ]

        class WINDOW_BUFFER_SIZE_RECORD(ctypes.Structure):
            _fields_ = [("dwSize", COORD)]

        class MENU_EVENT_RECORD(ctypes.Structure):
            _fields_ = [("dwCommandId", ctypes.wintypes.UINT)]

        class FOCUS_EVENT_RECORD(ctypes.Structure):
            _fields_ = [("bSetFocus", ctypes.wintypes.BOOL)]

        class INPUT_RECORD_EVENT(ctypes.Union):
            _fields_ = [
                ("KeyEvent", KEY_EVENT_RECORD),
                ("MouseEvent", MOUSE_EVENT_RECORD),
                ("WindowBufferSizeEvent", WINDOW_BUFFER_SIZE_RECORD),
                ("MenuEvent", MENU_EVENT_RECORD),
                ("FocusEvent", FOCUS_EVENT_RECORD),
            ]

        class INPUT_RECORD(ctypes.Structure):
            _fields_ = [
                ("EventType", ctypes.wintypes.WORD),
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
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING | ENABLE_PROCESSED_OUTPUT
        self._kernel32.SetConsoleMode(
            stdout_handle, mode.value | 0x0004 | 0x0001,
        )
        # Clear ENABLE_PROCESSED_INPUT (0x0001) on stdin so Ctrl+C arrives as
        # a KEY_EVENT (vk=0x43) rather than generating SIGINT, which would
        # bypass all coroutine-level exception handlers on Windows.
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

        # 等待输入就绪（最多 100ms）
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
            if record.EventType == self.KEY_EVENT:
                key_event = record.Event.KeyEvent
                if key_event.bKeyDown:
                    ctrl_state = key_event.dwControlKeyState
                    ctrl = bool(ctrl_state & 0x0008) or bool(
                        ctrl_state & 0x0004,
                    )
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


class _UnixBackend:
    """Unix (Linux / macOS) 控制台后端"""

    def __init__(self) -> None:
        self._old_settings: Optional[list] = None

    def init_console(self) -> None:
        """Unix 下无需特殊初始化"""

    def read_key_events(self) -> List[dict]:
        """
        Unix 下读取按键事件。

        使用 termios 的 raw 模式非阻塞读取，
        支持方向键等 ANSI 转义序列的解析。
        """
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        results: List[dict] = []

        try:
            tty.setraw(fd)
            # 非阻塞检查是否有输入
            readable, _, _ = select.select([fd], [], [], 0.1)
            if not readable:
                return results

            ch = os.read(fd, 1).decode("utf-8", errors="replace")

            if ch == "\x1b":
                # 可能是转义序列
                more, _, _ = select.select([fd], [], [], 0.05)
                if more:
                    ch2 = os.read(fd, 1).decode("utf-8", errors="replace")
                    if ch2 == "[":
                        ch3 = os.read(fd, 1).decode("utf-8", errors="replace")
                        arrow_map = {
                            "A": "up", "B": "down",
                            "C": "right", "D": "left",
                            "H": "home", "F": "end",
                            "3": "delete",
                        }
                        vk = arrow_map.get(ch3, "unknown")
                        # 消费 Delete 键的尾部 '~'
                        if ch3 == "3":
                            extra, _, _ = select.select([fd], [], [], 0.02)
                            if extra:
                                os.read(fd, 1)
                        results.append({
                            "type": "key", "vk": vk,
                            "char": "", "ctrl": False,
                        })
                    else:
                        results.append({
                            "type": "key", "vk": "escape",
                            "char": "", "ctrl": False,
                        })
                else:
                    results.append({
                        "type": "key", "vk": "escape",
                        "char": "", "ctrl": False,
                    })

            elif ch == "\r" or ch == "\n":
                results.append({
                    "type": "key", "vk": "return",
                    "char": "\r", "ctrl": False,
                })

            elif ch == "\x7f" or ch == "\x08":
                results.append({
                    "type": "key", "vk": "backspace",
                    "char": "", "ctrl": False,
                })

            elif ch == "\x03":
                results.append({
                    "type": "key", "vk": "interrupt",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x04":
                results.append({
                    "type": "key", "vk": "eof",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x01":
                results.append({
                    "type": "key", "vk": "home",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x05":
                results.append({
                    "type": "key", "vk": "end",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x15":
                results.append({
                    "type": "key", "vk": "clear_line",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x0b":
                results.append({
                    "type": "key", "vk": "kill_to_end",
                    "char": "", "ctrl": True,
                })

            elif ch == "\x17":
                results.append({
                    "type": "key", "vk": "delete_word",
                    "char": "", "ctrl": True,
                })

            elif ch == "\t":
                results.append({
                    "type": "key", "vk": "tab",
                    "char": "\t", "ctrl": False,
                })

            elif ord(ch) >= 32:
                # 对于多字节 UTF-8 字符，尝试读取后续字节
                full_char = ch
                if ord(ch) > 127:
                    # 尝试读取更多字节以组成完整 UTF-8 字符
                    more, _, _ = select.select([fd], [], [], 0.02)
                    if more:
                        extra = os.read(fd, 3).decode(
                            "utf-8", errors="replace",
                        )
                        full_char += extra
                results.append({
                    "type": "key", "vk": "char",
                    "char": full_char, "ctrl": False,
                })

            else:
                # 其他控制字符
                results.append({
                    "type": "key", "vk": f"ctrl_{ord(ch)}",
                    "char": ch, "ctrl": True,
                })

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        return results

    def getch(self) -> str:
        """Unix 下阻塞读取单个字符"""
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            # 处理转义序列
            if ch == "\x1b":
                import select
                more, _, _ = select.select([fd], [], [], 0.05)
                if more:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        sys.stdin.read(1)  # 消费方向键字符
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


# 全局后端实例（延迟初始化）
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

    # Windows 虚拟键码到标准名称的映射
    vk = event.get("vk", 0)
    ctrl = event.get("ctrl", False)
    char = event.get("char", "")

    vk_map = {
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

    if vk in vk_map:
        return {
            "type": "key",
            "vk": vk_map[vk],
            "char": char,
            "ctrl": ctrl,
        }

    # Ctrl 组合键
    if ctrl:
        ctrl_map = {
            0x43: "interrupt",   # Ctrl+C
            0x44: "eof",         # Ctrl+D
            0x55: "clear_line",  # Ctrl+U
            0x41: "home",        # Ctrl+A
            0x45: "end",         # Ctrl+E
            0x57: "delete_word", # Ctrl+W
            0x4B: "kill_to_end", # Ctrl+K
        }
        if vk in ctrl_map:
            return {
                "type": "key",
                "vk": ctrl_map[vk],
                "char": char,
                "ctrl": True,
            }

    # 可打印字符
    if char and ord(char) >= 32:
        return {
            "type": "key",
            "vk": "char",
            "char": char,
            "ctrl": False,
        }

    return event


# ══════════════════════════════════════════════════════════════════════════════
# 枚举与数据类
# ══════════════════════════════════════════════════════════════════════════════


class FontStyle(Enum):
    """字体样式枚举"""
    NORMAL = auto()
    COLOR = auto()
    ART = auto()
    BOX = auto()


class Alignment(Enum):
    """文本对齐方式"""
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


class BorderStyle(Enum):
    """边框样式"""
    SINGLE = auto()
    DOUBLE = auto()
    ROUNDED = auto()
    HEAVY = auto()
    NONE = auto()


class SpinnerStyle(Enum):
    """加载动画样式"""
    DOTS = auto()
    LINE = auto()
    CIRCLE = auto()
    ARROW = auto()
    BOUNCE = auto()
    PULSE = auto()


@dataclass(frozen=True)
class BorderChars:
    """边框字符集"""
    top_left: str
    top_right: str
    bottom_left: str
    bottom_right: str
    horizontal: str
    vertical: str
    t_left: str = ""
    t_right: str = ""
    t_top: str = ""
    t_bottom: str = ""
    cross: str = ""

    SINGLE: ClassVar[BorderChars]
    DOUBLE: ClassVar[BorderChars]
    ROUNDED: ClassVar[BorderChars]
    HEAVY: ClassVar[BorderChars]

    @classmethod
    def from_style(cls, style: BorderStyle) -> BorderChars:
        """根据样式获取边框字符集"""
        mapping: Dict[BorderStyle, BorderChars] = {
            BorderStyle.SINGLE: cls.SINGLE,
            BorderStyle.DOUBLE: cls.DOUBLE,
            BorderStyle.ROUNDED: cls.ROUNDED,
            BorderStyle.HEAVY: cls.HEAVY,
        }
        return mapping.get(style, cls.ROUNDED)


BorderChars.SINGLE = BorderChars(
    "┌", "┐", "└", "┘", "─", "│", "├", "┤", "┬", "┴", "┼",
)
BorderChars.DOUBLE = BorderChars(
    "╔", "╗", "╚", "╝", "═", "║", "╠", "╣", "╦", "╩", "╬",
)
BorderChars.ROUNDED = BorderChars(
    "╭", "╮", "╰", "╯", "─", "│", "├", "┤", "┬", "┴", "┼",
)
BorderChars.HEAVY = BorderChars(
    "┏", "┓", "┗", "┛", "━", "┃", "┣", "┫", "┳", "┻", "╋",
)


@dataclass(frozen=True)
class GradientTheme:
    """渐变主题配置 - 不可变数据类"""
    primary_start: RGB = (0, 170, 255)
    primary_end: RGB = (0, 255, 170)
    border_start: RGB = (0, 100, 180)
    border_end: RGB = (0, 180, 100)
    accent_start: RGB = (255, 200, 50)
    accent_end: RGB = (255, 150, 0)
    success: RGB = (0, 200, 100)
    warning: RGB = (255, 200, 0)
    error: RGB = (255, 80, 80)
    info: RGB = (100, 180, 255)
    muted: RGB = (128, 128, 128)

    @classmethod
    def default(cls) -> GradientTheme:
        """默认主题"""
        return cls()

    @classmethod
    def ocean(cls) -> GradientTheme:
        """海洋主题"""
        return cls(
            primary_start=(0, 119, 182), primary_end=(0, 180, 216),
            border_start=(0, 80, 140), border_end=(0, 140, 160),
            accent_start=(72, 202, 228), accent_end=(144, 224, 239),
        )

    @classmethod
    def sunset(cls) -> GradientTheme:
        """日落主题"""
        return cls(
            primary_start=(255, 100, 100), primary_end=(255, 180, 100),
            border_start=(180, 60, 60), border_end=(180, 120, 60),
            accent_start=(255, 200, 100), accent_end=(255, 150, 50),
        )

    @classmethod
    def forest(cls) -> GradientTheme:
        """森林主题"""
        return cls(
            primary_start=(34, 139, 34), primary_end=(144, 238, 144),
            border_start=(0, 100, 0), border_end=(60, 179, 113),
            accent_start=(50, 205, 50), accent_end=(173, 255, 47),
        )

    @classmethod
    def purple(cls) -> GradientTheme:
        """紫色主题"""
        return cls(
            primary_start=(138, 43, 226), primary_end=(255, 105, 180),
            border_start=(75, 0, 130), border_end=(199, 21, 133),
            accent_start=(186, 85, 211), accent_end=(255, 182, 193),
        )

    @classmethod
    def neon(cls) -> GradientTheme:
        """霓虹主题"""
        return cls(
            primary_start=(0, 255, 255), primary_end=(255, 0, 255),
            border_start=(0, 200, 200), border_end=(200, 0, 200),
            accent_start=(255, 255, 0), accent_end=(0, 255, 0),
        )

    @classmethod
    def monochrome(cls) -> GradientTheme:
        """单色主题"""
        return cls(
            primary_start=(200, 200, 200), primary_end=(255, 255, 255),
            border_start=(100, 100, 100), border_end=(180, 180, 180),
            accent_start=(220, 220, 220), accent_end=(255, 255, 255),
            muted=(80, 80, 80),
        )

    @classmethod
    def ruby(cls) -> GradientTheme:
        """红宝石主题"""
        return cls(
            primary_start=(220, 20, 60), primary_end=(255, 105, 97),
            border_start=(139, 0, 0), border_end=(178, 34, 34),
            accent_start=(255, 69, 0), accent_end=(255, 160, 122),
        )

    @classmethod
    def aurora(cls) -> GradientTheme:
        """极光主题"""
        return cls(
            primary_start=(0, 255, 127), primary_end=(0, 191, 255),
            border_start=(0, 200, 83), border_end=(30, 144, 255),
            accent_start=(127, 255, 212), accent_end=(135, 206, 250),
        )


@dataclass(frozen=True)
class SpinnerFrames:
    """加载动画帧序列"""
    frames: Tuple[str, ...]
    interval: float = 0.1

    DOTS: ClassVar[SpinnerFrames]
    LINE: ClassVar[SpinnerFrames]
    CIRCLE: ClassVar[SpinnerFrames]
    ARROW: ClassVar[SpinnerFrames]
    BOUNCE: ClassVar[SpinnerFrames]
    PULSE: ClassVar[SpinnerFrames]
    BRAILLE: ClassVar[SpinnerFrames]
    MOON: ClassVar[SpinnerFrames]
    CLOCK: ClassVar[SpinnerFrames]

    @classmethod
    def from_style(cls, style: SpinnerStyle) -> SpinnerFrames:
        """根据样式获取帧序列"""
        mapping: Dict[SpinnerStyle, SpinnerFrames] = {
            SpinnerStyle.DOTS: cls.DOTS,
            SpinnerStyle.LINE: cls.LINE,
            SpinnerStyle.CIRCLE: cls.CIRCLE,
            SpinnerStyle.ARROW: cls.ARROW,
            SpinnerStyle.BOUNCE: cls.BOUNCE,
            SpinnerStyle.PULSE: cls.PULSE,
        }
        return mapping.get(style, cls.DOTS)


SpinnerFrames.DOTS = SpinnerFrames((".", "..", "...", " "), 0.3)
SpinnerFrames.LINE = SpinnerFrames(("-", "\\", "|", "/"), 0.1)
SpinnerFrames.CIRCLE = SpinnerFrames(("◐", "◓", "◑", "◒"), 0.12)
SpinnerFrames.ARROW = SpinnerFrames(
    ("←", "↖", "↑", "↗", "→", "↘", "↓", "↙"), 0.1,
)
SpinnerFrames.BOUNCE = SpinnerFrames(
    ("⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈"), 0.08,
)
SpinnerFrames.PULSE = SpinnerFrames(("█", "▓", "▒", "░", "▒", "▓"), 0.12)
SpinnerFrames.BRAILLE = SpinnerFrames(
    ("⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"), 0.08,
)
SpinnerFrames.MOON = SpinnerFrames(
    ("🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"), 0.15,
)
SpinnerFrames.CLOCK = SpinnerFrames(
    ("🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"),
    0.12,
)


# ══════════════════════════════════════════════════════════════════════════════
# 日志写入器协议与实现
# ══════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class LogWriter(Protocol):
    """日志写入器协议"""

    def write(self, content: str) -> None:
        """写入日志内容"""
        ...


@dataclass
class FileLogWriter:
    """文件日志写入器"""
    file_path: str
    source_name: str = "consoleui"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def write(self, content: str) -> None:
        """线程安全地写入日志文件"""
        try:
            timestamp = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f",
            )[:-3]
            with self._lock, open(self.file_path, "a", encoding="utf-8") as f:
                for line in content.splitlines():
                    f.write(f"[{self.source_name}][{timestamp}] {line}\n")
        except OSError:
            pass


class NullLogWriter:
    """空日志写入器（无操作）"""

    def write(self, content: str) -> None:
        """空操作"""


class MultiLogWriter:
    """多路日志写入器"""

    def __init__(self, *writers: LogWriter) -> None:
        self._writers: Tuple[LogWriter, ...] = writers

    def write(self, content: str) -> None:
        """向所有写入器分发日志"""
        for writer in self._writers:
            writer.write(content)


class CallbackLogWriter:
    """回调日志写入器"""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback

    def write(self, content: str) -> None:
        """通过回调函数写入日志"""
        self._callback(content)


# ══════════════════════════════════════════════════════════════════════════════
# 终端信息工具
# ══════════════════════════════════════════════════════════════════════════════


def get_terminal_width() -> int:
    """安全获取终端宽度"""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def get_terminal_height() -> int:
    """安全获取终端高度"""
    try:
        return os.get_terminal_size().lines
    except OSError:
        return 24


def _write_flush(text: str) -> None:
    """写入 stdout 并立即刷新"""
    sys.stdout.write(text)
    sys.stdout.flush()


# ══════════════════════════════════════════════════════════════════════════════
# 文本工具类
# ══════════════════════════════════════════════════════════════════════════════


class TextUtils:
    """文本工具类 - 提供文本处理与测量的静态方法集合"""

    _ANSI_PATTERN: ClassVar[re.Pattern] = re.compile(r"\033\[[0-9;]*[a-zA-Z]")

    @staticmethod
    def display_width(text: str) -> int:
        """计算文本显示宽度（考虑全角字符和 ANSI 转义序列）"""
        cleaned = TextUtils.strip_ansi(text)
        width = wcswidth(cleaned)
        if width >= 0:
            return width
        # wcswidth 返回 -1 时逐字符计算
        total = 0
        for char in cleaned:
            w = wcwidth(char)
            total += w if w > 0 else 1
        return total

    @staticmethod
    def strip_ansi(text: str) -> str:
        """移除 ANSI 转义序列"""
        return TextUtils._ANSI_PATTERN.sub("", text)

    @staticmethod
    def pad_to_width(
        text: str,
        width: int,
        align: Alignment = Alignment.LEFT,
    ) -> str:
        """将文本填充到指定显示宽度"""
        current = TextUtils.display_width(text)
        padding = max(0, width - current)
        if align == Alignment.LEFT:
            return text + " " * padding
        if align == Alignment.RIGHT:
            return " " * padding + text
        left = padding // 2
        return " " * left + text + " " * (padding - left)

    @staticmethod
    def truncate(text: str, max_width: int, ellipsis: str = "...") -> str:
        """截断文本到指定宽度"""
        if TextUtils.display_width(text) <= max_width:
            return text
        ellipsis_width = TextUtils.display_width(ellipsis)
        result: List[str] = []
        current_width = 0
        for char in text:
            w = wcwidth(char)
            char_width = w if w > 0 else 1
            if current_width + char_width + ellipsis_width > max_width:
                break
            result.append(char)
            current_width += char_width
        return "".join(result) + ellipsis

    @staticmethod
    def truncate_start(text: str, max_width: int, ellipsis: str = "...") -> str:
        """截断文本：保留末尾，前面加省略号（适用于路径等）"""
        if TextUtils.display_width(text) <= max_width:
            return text
        ellipsis_width = TextUtils.display_width(ellipsis)
        if max_width <= ellipsis_width:
            return TextUtils.truncate(ellipsis, max_width)
        target = max_width - ellipsis_width
        picked: List[str] = []
        current_width = 0
        for char in reversed(text):
            w = wcwidth(char)
            char_width = w if w > 0 else 1
            if current_width + char_width > target:
                break
            picked.append(char)
            current_width += char_width
        return ellipsis + "".join(reversed(picked))

    @staticmethod
    def wrap_text(text: str, width: int) -> List[str]:
        """按显示宽度换行"""
        lines: List[str] = []
        for paragraph in text.splitlines():
            if not paragraph:
                lines.append("")
                continue
            current_line: List[str] = []
            current_width = 0
            for char in paragraph:
                w = wcwidth(char)
                char_width = w if w > 0 else 1
                if current_width + char_width > width and current_line:
                    lines.append("".join(current_line))
                    current_line = []
                    current_width = 0
                current_line.append(char)
                current_width += char_width
            if current_line:
                lines.append("".join(current_line))
        return lines

    @staticmethod
    def center_text(text: str, width: int, fill_char: str = " ") -> str:
        """居中文本"""
        text_width = TextUtils.display_width(text)
        if text_width >= width:
            return text
        total_padding = width - text_width
        left = total_padding // 2
        return fill_char * left + text + fill_char * (total_padding - left)


# ══════════════════════════════════════════════════════════════════════════════
# 渐变渲染器
# ══════════════════════════════════════════════════════════════════════════════


class GradientRenderer:
    """渐变渲染器 - 核心渲染引擎，负责所有颜色计算与渲染"""

    BORDER_CHARS: ClassVar[frozenset] = frozenset(
        "╚═╝╗║╔╭╮╰╯─│┌┐└┘├┤┬┴┼━┃┏┓┗┛┣┫┳┻╋╠╣╦╩╬",
    )

    def __init__(
        self,
        theme: GradientTheme,
        reference_width: int = 80,
    ) -> None:
        self.theme = theme
        self.reference_width = reference_width
        self._color_cache: Dict[Tuple[RGB, RGB, int], RGB] = {}

    def update_reference_width(self, width: Optional[int] = None) -> None:
        """更新参考宽度"""
        self.reference_width = width if width is not None else get_terminal_width()

    def clear_cache(self) -> None:
        """清空颜色插值缓存"""
        self._color_cache.clear()

    def _interpolate_cached(
        self, start: RGB, end: RGB, factor: float,
    ) -> RGB:
        """带缓存的颜色插值"""
        quantized = int(max(0.0, min(1.0, factor)) * 255)
        key = (start, end, quantized)
        cached = self._color_cache.get(key)
        if cached is not None:
            return cached
        f = quantized / 255.0
        result = (
            int(start[0] + (end[0] - start[0]) * f),
            int(start[1] + (end[1] - start[1]) * f),
            int(start[2] + (end[2] - start[2]) * f),
        )
        self._color_cache[key] = result
        return result

    @staticmethod
    def interpolate(start: RGB, end: RGB, factor: float) -> RGB:
        """颜色插值（纯函数版本）"""
        factor = max(0.0, min(1.0, factor))
        return (
            int(start[0] + (end[0] - start[0]) * factor),
            int(start[1] + (end[1] - start[1]) * factor),
            int(start[2] + (end[2] - start[2]) * factor),
        )

    @staticmethod
    def interpolate_multi(colors: Sequence[RGB], factor: float) -> RGB:
        """多色渐变插值"""
        if not colors:
            return (255, 255, 255)
        if len(colors) == 1:
            return colors[0]
        factor = max(0.0, min(1.0, factor))
        segment_count = len(colors) - 1
        scaled = factor * segment_count
        index = min(int(scaled), segment_count - 1)
        local_factor = scaled - index
        return GradientRenderer.interpolate(
            colors[index], colors[index + 1], local_factor,
        )

    def _diagonal_factor(self, col: int, row: int, max_diag: int) -> float:
        """计算对角线渐变因子"""
        return (col + row) / max_diag if max_diag > 0 else 0.0

    def color_for_char(
        self, index: int, total: int, is_border: bool = False,
    ) -> RGB:
        """计算单个字符的渐变颜色"""
        ref_len = max(total, 30)
        factor = index / (ref_len - 1) if ref_len > 1 else 0.0
        if is_border:
            return self._interpolate_cached(
                self.theme.border_start, self.theme.border_end, factor,
            )
        return self._interpolate_cached(
            self.theme.primary_start, self.theme.primary_end, factor,
        )

    def color_for_accent(self, index: int, total: int) -> RGB:
        """计算强调色渐变"""
        ref_len = max(total, 30)
        factor = index / (ref_len - 1) if ref_len > 1 else 0.0
        return self._interpolate_cached(
            self.theme.accent_start, self.theme.accent_end, factor,
        )

    def rgb_fg(self, r: int, g: int, b: int) -> str:
        """RGB 转 ANSI 前景色序列"""
        return f"\033[38;2;{r};{g};{b}m"

    def rgb_bg(self, r: int, g: int, b: int) -> str:
        """RGB 转 ANSI 背景色序列"""
        return f"\033[48;2;{r};{g};{b}m"

    def render_text_ansi(
        self,
        text: str,
        start_index: int = 0,
        total_length: Optional[int] = None,
        is_border: bool = False,
    ) -> str:
        """渲染文本为 ANSI 转义字符串（水平渐变）"""
        if not text:
            return ""

        total = total_length or (start_index + len(text))
        ref_len = max(total, 30)
        start = self.theme.border_start if is_border else self.theme.primary_start
        end = self.theme.border_end if is_border else self.theme.primary_end
        parts: List[str] = []

        for i, char in enumerate(text):
            factor = (start_index + i) / (ref_len - 1) if ref_len > 1 else 0.0
            r, g, b = self._interpolate_cached(start, end, factor)
            parts.append(f"\033[38;2;{r};{g};{b}m{char}")

        parts.append(ANSI_RESET)
        return "".join(parts)

    def render_text_solid(self, text: str, color: RGB) -> str:
        """渲染纯色文本"""
        r, g, b = color
        return f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}"

    def render_banner(
        self,
        text: str,
        use_border_colors: bool = True,
        row_offset: int = 0,
    ) -> Text:
        """渲染横幅文本（多行对角线渐变，使用 Rich Text）"""
        lines = text.splitlines()
        if not lines:
            return Text()

        height = len(lines)
        width = max((len(line) for line in lines), default=0)
        ref_width = max(width, self.reference_width // 2)
        max_diag = ref_width + height - 2
        result = Text()

        for row_idx, line in enumerate(lines):
            actual_row = row_offset + row_idx
            for col_idx, char in enumerate(line):
                is_border = char in self.BORDER_CHARS
                factor = self._diagonal_factor(col_idx, actual_row, max_diag)
                if is_border and use_border_colors:
                    color = self._interpolate_cached(
                        self.theme.border_start, self.theme.border_end, factor,
                    )
                else:
                    color = self._interpolate_cached(
                        self.theme.primary_start, self.theme.primary_end, factor,
                    )
                result.append(
                    char, style=f"rgb({color[0]},{color[1]},{color[2]})",
                )
            if row_idx < height - 1:
                result.append("\n")

        return result

    def render_line(
        self,
        text: str,
        col_offset: int = 0,
        row: int = 0,
        is_border: bool = False,
    ) -> Text:
        """渲染单行文本（Rich Text，对角线渐变）"""
        result = Text()
        ref_width = max(len(text) + col_offset, self.reference_width // 2)
        max_diag = ref_width + 20

        for i, char in enumerate(text):
            factor = self._diagonal_factor(col_offset + i, row, max_diag)
            if is_border or char in self.BORDER_CHARS:
                color = self._interpolate_cached(
                    self.theme.border_start, self.theme.border_end, factor,
                )
            else:
                color = self._interpolate_cached(
                    self.theme.primary_start, self.theme.primary_end, factor,
                )
            result.append(
                char, style=f"rgb({color[0]},{color[1]},{color[2]})",
            )

        return result

    def render_progress_bar(
        self,
        progress: float,
        width: int = 30,
        filled_char: str = "━",
        empty_char: str = "─",
        head_char: str = "╸",
    ) -> str:
        """渲染渐变进度条（ANSI）"""
        progress = max(0.0, min(1.0, progress))
        filled_count = int(width * progress)
        empty_count = width - filled_count
        parts: List[str] = []

        for i in range(filled_count):
            factor = i / max(width - 1, 1)
            r, g, b = self._interpolate_cached(
                self.theme.primary_start, self.theme.primary_end, factor,
            )
            parts.append(f"\033[38;2;{r};{g};{b}m{filled_char}")

        if filled_count < width:
            factor = filled_count / max(width - 1, 1)
            r, g, b = self._interpolate_cached(
                self.theme.primary_start, self.theme.primary_end, factor,
            )
            parts.append(f"\033[38;2;{r};{g};{b}m{head_char}")
            empty_count -= 1

        if empty_count > 0:
            mr, mg, mb = self.theme.muted
            parts.append(f"\033[38;2;{mr};{mg};{mb}m{empty_char * empty_count}")

        parts.append(ANSI_RESET)
        return "".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# 盒子构建器
# ══════════════════════════════════════════════════════════════════════════════


class BoxBuilder:
    """盒子构建器 - 支持多种边框样式"""

    def __init__(
        self,
        renderer: GradientRenderer,
        padding: int = 1,
        border_style: BorderStyle = BorderStyle.ROUNDED,
    ) -> None:
        self.renderer = renderer
        self.padding = padding
        self.border_style = border_style

    def build(
        self,
        text: str,
        prefix: str = "",
        row_offset: int = 0,
        title: str = "",
        min_width: int = 0,
    ) -> List[Text]:
        """构建文本盒子"""
        chars = BorderChars.from_style(self.border_style)
        lines = text.strip().splitlines()
        if not lines:
            return []

        prefix_width = TextUtils.display_width(prefix)
        processed: List[str] = []
        for idx, line in enumerate(lines):
            content = line.strip()
            if content:
                if idx == 0 and prefix:
                    processed.append(f"{prefix} {content}")
                else:
                    indent = " " * (prefix_width + 1) if prefix else ""
                    processed.append(f"{indent}{content}")
            else:
                processed.append("")

        max_content_width = max(
            (TextUtils.display_width(line) for line in processed), default=0,
        )
        if title:
            max_content_width = max(
                max_content_width, TextUtils.display_width(title) + 4,
            )
        max_content_width = max(max_content_width, min_width)
        term_width = get_terminal_width()
        max_content_width = min(
            max(max_content_width, 20), max(term_width - 4, 8),
        )

        display_lines: List[str] = []
        for line in processed:
            if not line:
                display_lines.append("")
                continue
            if TextUtils.display_width(line) <= max_content_width:
                display_lines.append(line)
            else:
                display_lines.extend(
                    TextUtils.wrap_text(line, max_content_width) or [""],
                )

        box_inner_width = max_content_width + self.padding * 2

        # 构建顶边
        if title:
            title_decorated = f" {title} "
            title_dw = TextUtils.display_width(title_decorated)
            left_bar = chars.horizontal * 2
            right_bar = chars.horizontal * max(0, box_inner_width - 2 - title_dw)
            top_str = (
                f"{chars.top_left}{left_bar}{title_decorated}"
                f"{right_bar}{chars.top_right}"
            )
        else:
            top_str = (
                f"{chars.top_left}"
                f"{chars.horizontal * box_inner_width}"
                f"{chars.top_right}"
            )

        bottom_str = (
            f"{chars.bottom_left}"
            f"{chars.horizontal * box_inner_width}"
            f"{chars.bottom_right}"
        )

        result: List[Text] = [
            self.renderer.render_line(top_str, row=row_offset, is_border=True),
        ]

        for idx, content in enumerate(display_lines):
            row = row_offset + idx + 1
            line = Text()
            line.append_text(
                self.renderer.render_line(
                    chars.vertical, row=row, is_border=True,
                ),
            )
            line.append(" " * self.padding)
            line.append(content)
            pad_right = max(0, max_content_width - TextUtils.display_width(content))
            line.append(" " * pad_right)
            line.append(" " * self.padding)
            line.append_text(
                self.renderer.render_line(
                    chars.vertical,
                    col_offset=box_inner_width + 1,
                    row=row,
                    is_border=True,
                ),
            )
            result.append(line)

        result.append(
            self.renderer.render_line(
                bottom_str,
                row=row_offset + len(display_lines) + 1,
                is_border=True,
            ),
        )
        return result


# ══════════════════════════════════════════════════════════════════════════════
# ASCII 艺术字构建器
# ══════════════════════════════════════════════════════════════════════════════


class AsciiArtBuilder:
    """ASCII 艺术字构建器"""

    def __init__(
        self,
        renderer: GradientRenderer,
        char_map: Dict[str, List[str]],
    ) -> None:
        self.renderer = renderer
        self.char_map = char_map

    def build(
        self,
        text: str,
        row_offset: int = 0,
        max_width: Optional[int] = None,
    ) -> Tuple[Text, int]:
        """构建 ASCII 艺术字；超宽时按终端列数自动换行"""
        text = text.upper()
        line_count = 6
        lines = [""] * line_count

        for char in text:
            if char in self.char_map:
                char_lines = self.char_map[char]
                for i in range(min(line_count, len(char_lines))):
                    lines[i] += char_lines[i]
            else:
                for i in range(line_count):
                    lines[i] += " "

        term_width = max_width if max_width is not None else get_terminal_width()
        content_width = max(term_width - 2, 8)
        wrapped_lines: List[str] = []
        for line in lines:
            if TextUtils.display_width(line) <= content_width:
                wrapped_lines.append(line)
            else:
                wrapped_lines.extend(
                    TextUtils.wrap_text(line, content_width) or [""],
                )

        banner = self.renderer.render_banner(
            "\n".join(wrapped_lines),
            use_border_colors=True,
            row_offset=row_offset,
        )
        return banner, len(wrapped_lines)


# ══════════════════════════════════════════════════════════════════════════════
# 流式输出器
# ══════════════════════════════════════════════════════════════════════════════


class StreamWriter:
    """流式输出器 - 支持逐字符渐变输出"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode
        self._char_index: int = 0

    def reset(self) -> None:
        """重置内部状态"""
        self._char_index = 0

    def write_char(self, char: str, total_length: int = 100) -> None:
        """写入单个字符（带渐变色）"""
        if self.normal_mode or char == "\n":
            sys.stdout.write(char)
        else:
            r, g, b = self.renderer.color_for_char(
                self._char_index, total_length,
            )
            sys.stdout.write(f"\033[38;2;{r};{g};{b}m{char}")
        sys.stdout.flush()
        self._char_index += 1

    def write_text(self, text: str, delay: float = 0.02) -> int:
        """同步流式写入文本，返回换行数"""
        lines = 0
        total = len(text)
        for char in text:
            if char == "\n":
                _write_flush(f"{ANSI_RESET}\n")
                lines += 1
                self._char_index = 0
            else:
                self.write_char(char, total)
            if delay > 0:
                time.sleep(delay)
        _write_flush(ANSI_RESET)
        return lines

    async def write_text_async(self, text: str, delay: float = 0.02) -> int:
        """异步流式写入文本，返回换行数"""
        lines = 0
        total = len(text)
        for char in text:
            if char == "\n":
                _write_flush(f"{ANSI_RESET}\n")
                lines += 1
                self._char_index = 0
            else:
                self.write_char(char, total)
            if delay > 0:
                await asyncio.sleep(delay)
        _write_flush(ANSI_RESET)
        return lines

    def iter_chars(self, text: str) -> Iterator[Tuple[str, RGB]]:
        """迭代字符及其对应颜色"""
        total = len(text)
        for i, char in enumerate(text):
            yield char, self.renderer.color_for_char(i, total)

    async def aiter_chars(self, text: str) -> AsyncIterator[Tuple[str, RGB]]:
        """异步迭代字符及其对应颜色"""
        total = len(text)
        for i, char in enumerate(text):
            yield char, self.renderer.color_for_char(i, total)


# ══════════════════════════════════════════════════════════════════════════════
# 行编辑器（统一平台逻辑）
# ══════════════════════════════════════════════════════════════════════════════


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
        buf = state.buffer
        pos = state.cursor_pos

        if vk == "return":
            return "".join(buf)

        if vk == "interrupt":
            raise KeyboardInterrupt

        if vk == "eof":
            raise EOFError

        if vk == "clear_line":
            state.buffer = []
            state.cursor_pos = 0
            return None

        if vk == "home":
            state.cursor_pos = 0
            return None

        if vk == "end":
            state.cursor_pos = len(buf)
            return None

        if vk == "kill_to_end":
            state.buffer = list(buf[:pos])
            return None

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
            return None

        if vk == "backspace":
            if pos > 0:
                buf.pop(pos - 1)
                state.cursor_pos = pos - 1
            return None

        if vk == "delete":
            if pos < len(buf):
                buf.pop(pos)
            return None

        if vk == "left":
            if pos > 0:
                state.cursor_pos = pos - 1
            return None

        if vk == "right":
            if pos < len(buf):
                state.cursor_pos = pos + 1
            return None

        if vk == "up":
            if history:
                if state.history_index == -1:
                    state.saved_input = "".join(buf)
                    new_idx = len(history) - 1
                elif state.history_index > 0:
                    new_idx = state.history_index - 1
                else:
                    return None
                state.history_index = new_idx
                state.buffer = list(history[new_idx])
                state.cursor_pos = len(state.buffer)
            return None

        if vk == "down":
            if state.history_index >= 0:
                if state.history_index < len(history) - 1:
                    state.history_index += 1
                    state.buffer = list(history[state.history_index])
                    state.cursor_pos = len(state.buffer)
                else:
                    state.history_index = -1
                    state.buffer = list(state.saved_input)
                    state.cursor_pos = len(state.buffer)
                    state.saved_input = ""
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

    async def _interactive_readline(self, prompt: str) -> str:
        """通过平台后端交互式读取输入"""
        backend = _get_backend()
        state = _LineEditorState()
        self._last_drawn = ""
        self._draw_line(prompt, state)
        loop = asyncio.get_running_loop()

        try:
            while True:
                raw_events = await loop.run_in_executor(
                    None, backend.read_key_events,
                )
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
                    result = _LineEditor.process_event(
                        event, state, self._history,
                    )
                    if result is not None:
                        self._finish_line()
                        return result
                    dirty = True

                if dirty:
                    buf = "".join(state.buffer)
                    ghost = ""
                    if self._completer and buf:
                        cands = self._completer(buf)
                        if cands:
                            lcp = cands[0] if len(cands) == 1 else _longest_common_prefix(cands)
                            if lcp.startswith(buf):
                                ghost = lcp[len(buf):]
                    self._draw_line(prompt, state, ghost=ghost)

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


# ══════════════════════════════════════════════════════════════════════════════
# 交互式选择器
# ══════════════════════════════════════════════════════════════════════════════


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
                    vk = event.get("vk", "")

                    if vk == "return":
                        self._clear_options(total_lines)
                        self._draw_final_selection(options[current])
                        return SelectionResult(current, options[current])

                    if vk == "up":
                        current = (current - 1) % len(options)
                        self._clear_options(total_lines)
                        self._draw_options(options, current)

                    elif vk == "down":
                        current = (current + 1) % len(options)
                        self._clear_options(total_lines)
                        self._draw_options(options, current)

                    elif vk == "escape":
                        self._clear_options(total_lines)
                        return SelectionResult(-1, "")

                    elif vk == "interrupt":
                        self._clear_options(total_lines)
                        raise KeyboardInterrupt

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


# ══════════════════════════════════════════════════════════════════════════════
# 进度条
# ══════════════════════════════════════════════════════════════════════════════


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
            parts.append(
                self.renderer.render_progress_bar(progress, self.width),
            )

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
                elapsed_str = (
                    f"\033[38;2;{mr};{mg};{mb}m {elapsed_str}{ANSI_RESET}"
                )
            else:
                elapsed_str = f" {elapsed_str}"
            parts.append(elapsed_str)

        if self.show_rate and elapsed > 0:
            rate = self._current / elapsed
            rate_str = f" ({rate:.1f}/s)"
            if not self.normal_mode:
                mr, mg, mb = self.renderer.theme.muted
                rate_str = (
                    f"\033[38;2;{mr};{mg};{mb}m{rate_str}{ANSI_RESET}"
                )
            parts.append(rate_str)

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


# ══════════════════════════════════════════════════════════════════════════════
# 表格构建器
# ══════════════════════════════════════════════════════════════════════════════


class TableBuilder:
    """
    渐变表格构建器 - 支持自动列宽、对齐、标题等

    用法：
      table = ui.table(["Name", "Age", "City"])
      table.add_row(["Alice", "30", "NYC"])
      table.add_row(["Bob", "25", "LA"])
      table.render()
    """

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        headers: Optional[Sequence[str]] = None,
        border_style: BorderStyle = BorderStyle.ROUNDED,
        normal_mode: bool = False,
        min_col_width: int = 3,
        padding: int = 1,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.headers = list(headers) if headers else []
        self.border_style = border_style
        self.normal_mode = normal_mode
        self.min_col_width = min_col_width
        self.padding = padding
        self._rows: List[List[str]] = []
        self._alignments: List[Alignment] = []

    def add_row(self, row: Sequence[str]) -> TableBuilder:
        """添加一行数据"""
        self._rows.append(list(row))
        return self

    def add_rows(self, rows: Sequence[Sequence[str]]) -> TableBuilder:
        """批量添加行"""
        for row in rows:
            self._rows.append(list(row))
        return self

    def set_alignments(self, *alignments: Alignment) -> TableBuilder:
        """设置列对齐方式"""
        self._alignments = list(alignments)
        return self

    def render(self, row_offset: int = 0) -> int:
        """渲染表格，返回占用的行数"""
        chars = BorderChars.from_style(self.border_style)

        col_count = max(
            len(self.headers),
            max((len(row) for row in self._rows), default=0),
        )
        if col_count == 0:
            return 0

        # 标准化行
        all_rows = [
            row + [""] * (col_count - len(row)) for row in self._rows
        ]
        header_row = self.headers + [""] * (col_count - len(self.headers))

        # 计算列宽
        col_widths: List[int] = []
        for c in range(col_count):
            header_w = TextUtils.display_width(header_row[c]) if self.headers else 0
            data_w = max(
                (TextUtils.display_width(row[c]) for row in all_rows),
                default=0,
            )
            col_widths.append(max(header_w, data_w, self.min_col_width))

        alignments = list(self._alignments) + [Alignment.LEFT] * (
            col_count - len(self._alignments)
        )

        pad = " " * self.padding
        current_row = row_offset
        lines = 0

        def _make_separator(
            left: str, mid: str, right: str,
        ) -> str:
            parts = [
                chars.horizontal * (w + self.padding * 2)
                for w in col_widths
            ]
            return left + mid.join(parts) + right

        # 顶边
        top = _make_separator(
            chars.top_left,
            chars.t_top or chars.horizontal,
            chars.top_right,
        )
        self.console.print(
            self.renderer.render_line(top, row=current_row, is_border=True),
        )
        current_row += 1
        lines += 1

        # 表头
        if self.headers:
            ht = Text()
            ht.append_text(
                self.renderer.render_line(
                    chars.vertical, row=current_row, is_border=True,
                ),
            )
            for i, (hdr, width, align) in enumerate(
                zip(header_row, col_widths, alignments),
            ):
                ht.append(pad)
                padded = TextUtils.pad_to_width(hdr, width, align)
                for ci, ch in enumerate(padded):
                    factor = ci / max(width - 1, 1)
                    r, g, b = self.renderer._interpolate_cached(
                        self.renderer.theme.accent_start,
                        self.renderer.theme.accent_end,
                        factor,
                    )
                    ht.append(ch, style=f"bold rgb({r},{g},{b})")
                ht.append(pad)
                ht.append_text(
                    self.renderer.render_line(
                        chars.vertical, row=current_row, is_border=True,
                    ),
                )
            self.console.print(ht)
            current_row += 1
            lines += 1

            # 表头分隔线
            sep = _make_separator(
                chars.t_left or chars.vertical,
                chars.cross or chars.horizontal,
                chars.t_right or chars.vertical,
            )
            self.console.print(
                self.renderer.render_line(
                    sep, row=current_row, is_border=True,
                ),
            )
            current_row += 1
            lines += 1

        # 数据行
        for row_data in all_rows:
            rt = Text()
            rt.append_text(
                self.renderer.render_line(
                    chars.vertical, row=current_row, is_border=True,
                ),
            )
            for i, (cell, width, align) in enumerate(
                zip(row_data, col_widths, alignments),
            ):
                rt.append(pad)
                padded = TextUtils.pad_to_width(cell, width, align)
                rt.append_text(
                    self.renderer.render_line(
                        padded, col_offset=i * 10, row=current_row,
                    ),
                )
                rt.append(pad)
                rt.append_text(
                    self.renderer.render_line(
                        chars.vertical, row=current_row, is_border=True,
                    ),
                )
            self.console.print(rt)
            current_row += 1
            lines += 1

        # 底边
        bottom = _make_separator(
            chars.bottom_left,
            chars.t_bottom or chars.horizontal,
            chars.bottom_right,
        )
        self.console.print(
            self.renderer.render_line(
                bottom, row=current_row, is_border=True,
            ),
        )
        lines += 1

        return lines


# ══════════════════════════════════════════════════════════════════════════════
# 面板（Panel）
# ══════════════════════════════════════════════════════════════════════════════


class PanelBuilder:
    """面板构建器 - 带标题和边框的内容区域"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        border_style: BorderStyle = BorderStyle.ROUNDED,
        normal_mode: bool = False,
        padding: int = 1,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.border_style = border_style
        self.normal_mode = normal_mode
        self.padding = padding

    def render(
        self,
        content: str,
        title: str = "",
        subtitle: str = "",
        width: Optional[int] = None,
        row_offset: int = 0,
    ) -> int:
        """渲染面板，返回行数"""
        chars = BorderChars.from_style(self.border_style)
        content_lines = content.strip().splitlines()
        term_width = get_terminal_width()

        if width is None:
            max_content = max(
                (TextUtils.display_width(line) for line in content_lines),
                default=0,
            )
            title_w = TextUtils.display_width(title) + 4 if title else 0
            sub_w = TextUtils.display_width(subtitle) + 4 if subtitle else 0
            inner_width = min(
                max(max_content, title_w, sub_w, 20), term_width - 4,
            )
        else:
            inner_width = width - 2 - self.padding * 2

        box_inner = inner_width + self.padding * 2
        current_row = row_offset
        lines_rendered = 0

        # 顶边
        if title:
            td = f" {title} "
            td_w = TextUtils.display_width(td)
            top_str = (
                f"{chars.top_left}"
                f"{chars.horizontal * 2}{td}"
                f"{chars.horizontal * max(0, box_inner - 2 - td_w)}"
                f"{chars.top_right}"
            )
        else:
            top_str = (
                f"{chars.top_left}"
                f"{chars.horizontal * box_inner}"
                f"{chars.top_right}"
            )

        self.console.print(
            self.renderer.render_line(
                top_str, row=current_row, is_border=True,
            ),
        )
        current_row += 1
        lines_rendered += 1

        # 内容行
        for line_text in content_lines:
            wrapped = TextUtils.wrap_text(line_text, inner_width) or [""]
            for wl in wrapped:
                row_rich = Text()
                row_rich.append_text(
                    self.renderer.render_line(
                        chars.vertical, row=current_row, is_border=True,
                    ),
                )
                row_rich.append(" " * self.padding)
                row_rich.append_text(
                    self.renderer.render_line(wl, row=current_row),
                )
                pad_right = inner_width - TextUtils.display_width(wl)
                row_rich.append(" " * max(0, pad_right))
                row_rich.append(" " * self.padding)
                row_rich.append_text(
                    self.renderer.render_line(
                        chars.vertical,
                        col_offset=box_inner + 1,
                        row=current_row,
                        is_border=True,
                    ),
                )
                self.console.print(row_rich)
                current_row += 1
                lines_rendered += 1

        # 底边
        if subtitle:
            sd = f" {subtitle} "
            sd_w = TextUtils.display_width(sd)
            bottom_str = (
                f"{chars.bottom_left}"
                f"{chars.horizontal * max(0, box_inner - 2 - sd_w)}"
                f"{sd}"
                f"{chars.horizontal * 2}"
                f"{chars.bottom_right}"
            )
        else:
            bottom_str = (
                f"{chars.bottom_left}"
                f"{chars.horizontal * box_inner}"
                f"{chars.bottom_right}"
            )

        self.console.print(
            self.renderer.render_line(
                bottom_str, row=current_row, is_border=True,
            ),
        )
        lines_rendered += 1

        return lines_rendered


# ══════════════════════════════════════════════════════════════════════════════
# 分隔线
# ══════════════════════════════════════════════════════════════════════════════


class Divider:
    """渐变分隔线"""

    def __init__(
        self,
        renderer: GradientRenderer,
        console: Console,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.console = console
        self.normal_mode = normal_mode

    def render(
        self,
        char: str = "─",
        width: Optional[int] = None,
        title: str = "",
        row: int = 0,
    ) -> None:
        """渲染分隔线"""
        actual_width = width or get_terminal_width()

        if title:
            td = f" {title} "
            td_w = TextUtils.display_width(td)
            left_len = max(0, (actual_width - td_w) // 2)
            right_len = max(0, actual_width - td_w - left_len)
            line = char * left_len + td + char * right_len
        else:
            line = char * actual_width

        if self.normal_mode:
            print(line)
        else:
            self.console.print(
                self.renderer.render_line(line, row=row, is_border=True),
            )


# ══════════════════════════════════════════════════════════════════════════════
# 计时器
# ══════════════════════════════════════════════════════════════════════════════


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
                    self.console.print(
                        self.renderer.render_line(line),
                    )

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

            key = await loop.run_in_executor(None, backend.getch)

            if key in ("q", "Q", "\x1b"):
                _write_flush(ANSI_CLEAR_SCREEN)
                break
            elif key in ("n", "N", " ", "\r"):
                if current_page < total_pages - 1:
                    current_page += 1
            elif key in ("p", "P"):
                if current_page > 0:
                    current_page -= 1


# ══════════════════════════════════════════════════════════════════════════════
# 倒计时
# ══════════════════════════════════════════════════════════════════════════════


class Countdown:
    """倒计时组件"""

    def __init__(
        self,
        renderer: GradientRenderer,
        normal_mode: bool = False,
    ) -> None:
        self.renderer = renderer
        self.normal_mode = normal_mode

    async def run(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
        on_tick: Optional[Callable[[int], Awaitable[None]]] = None,
    ) -> None:
        """异步倒计时"""
        for remaining in range(seconds, 0, -1):
            text = message.format(seconds=remaining)

            if self.normal_mode:
                _write_flush(f"\r{text} ")
            else:
                factor = 1.0 - (remaining / seconds)
                r, g, b = self.renderer._interpolate_cached(
                    self.renderer.theme.warning,
                    self.renderer.theme.success,
                    factor,
                )
                _write_flush(
                    f"{ANSI_CLEAR_LINE}"
                    f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}",
                )

            if on_tick is not None:
                await on_tick(remaining)

            await asyncio.sleep(1.0)

        _write_flush(ANSI_CLEAR_LINE)

    def run_sync(
        self,
        seconds: int,
        message: str = "Starting in {seconds}s...",
    ) -> None:
        """同步倒计时"""
        for remaining in range(seconds, 0, -1):
            text = message.format(seconds=remaining)
            if self.normal_mode:
                _write_flush(f"\r{text} ")
            else:
                factor = 1.0 - (remaining / seconds)
                r, g, b = self.renderer._interpolate_cached(
                    self.renderer.theme.warning,
                    self.renderer.theme.success,
                    factor,
                )
                _write_flush(
                    f"{ANSI_CLEAR_LINE}"
                    f"\033[38;2;{r};{g};{b}m{text}{ANSI_RESET}",
                )
            time.sleep(1.0)

        _write_flush(ANSI_CLEAR_LINE)


# ══════════════════════════════════════════════════════════════════════════════
# 列布局
# ══════════════════════════════════════════════════════════════════════════════


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


# ══════════════════════════════════════════════════════════════════════════════
# 树形视图
# ══════════════════════════════════════════════════════════════════════════════


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


# ══════════════════════════════════════════════════════════════════════════════
# 主类：ConsoleUI
# ══════════════════════════════════════════════════════════════════════════════


class ConsoleUI:
    """
    控制台UI主类 - 高性能异步控制台UI框架

    核心特性：
      - 调用链模式: ui.print("Hello").box("World").newline()
      - 流式输出: ui.stream("Loading...")
      - 异步输入: await ui.input_async("> ")
      - 交互式选择: await ui.select("Choose:", options)
      - 进度条: with ui.progress("Loading", total=100) as pb: ...
      - Spinner: async with ui.spinner("Working...") as sp: ...
      - 表格: ui.table(headers).add_row(data).render()
      - 面板: ui.panel(content, title="Info")
      - 分隔线: ui.divider()
      - 确认对话框: await ui.confirm("Are you sure?")
      - 计时器: with ui.timer("Task") as t: ...
      - 通知: ui.success("Done") / ui.warning("Caution")
      - 键值对: ui.kv_list({"key": "value"})
      - 多行输入: await ui.multiline_input()
      - 分页: await ui.page(long_text)
      - 倒计时: await ui.countdown(5)
      - 列布局: ui.columns([col1, col2])
      - 树形视图: ui.tree(root_node)
    """

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

        # 初始化所有子组件
        self._box_builder = BoxBuilder(
            self._renderer, border_style=border_style,
        )
        self._art_builder = AsciiArtBuilder(self._renderer, self._char_map)
        self._input_handler = AsyncInput(
            self._renderer, self._console, normal_mode,
            completer=self._complete_command,
            history_path=Path.home() / ".star_cursor_history",
        )
        self._stream_writer = StreamWriter(self._renderer, normal_mode)
        self._selector = InteractiveSelector(self._renderer, normal_mode)
        self._confirm_dialog = ConfirmDialog(self._renderer, normal_mode)
        self._notification = Notification(self._renderer, normal_mode)
        self._divider = Divider(
            self._renderer, self._console, normal_mode,
        )
        self._panel_builder = PanelBuilder(
            self._renderer, self._console, border_style, normal_mode,
        )
        self._kv_list = KeyValueList(self._renderer, normal_mode)
        self._multiline_input = MultiLineInput(self._renderer, normal_mode)
        self._pager = Pager(
            self._renderer, self._console, normal_mode,
        )
        self._countdown = Countdown(self._renderer, normal_mode)
        self._column_layout = ColumnLayout(
            self._renderer, self._console, normal_mode,
        )
        self._tree_view = TreeView(
            self._renderer, self._console, normal_mode,
        )

        self._line_count: int = 0
        self._commands: Dict[str, Dict[str, Any]] = {}

    # ══════════════════════════════════════════════════════════════════════════
    # 属性
    # ══════════════════════════════════════════════════════════════════════════

    @property
    def line_count(self) -> int:
        """已输出的行数"""
        return self._line_count

    @property
    def theme(self) -> GradientTheme:
        """当前主题"""
        return self._theme

    @property
    def commands(self) -> Dict[str, Dict[str, Any]]:
        """注册的命令（副本）"""
        return self._commands.copy()

    def _complete_command(self, prefix: str) -> List[str]:
        has_slash = prefix.startswith("/")
        search = prefix if has_slash else "/" + prefix
        matches = [k for k in self._commands if k.startswith(search)]
        return matches if has_slash else [k[1:] for k in matches]

    @property
    def renderer(self) -> GradientRenderer:
        """获取渲染器（高级用法）"""
        return self._renderer

    @property
    def console(self) -> Console:
        """获取 Rich Console 实例"""
        return self._console

    @property
    def is_normal_mode(self) -> bool:
        """是否为普通模式"""
        return self._normal_mode

    # ══════════════════════════════════════════════════════════════════════════
    # 配置方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def set_theme(self, theme: GradientTheme) -> ConsoleUI:
        """设置主题"""
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
        """设置 ASCII 艺术字符映射"""
        self._char_map = char_map
        self._art_builder = AsciiArtBuilder(self._renderer, char_map)
        return self

    def set_border_style(self, style: BorderStyle) -> ConsoleUI:
        """设置默认边框样式"""
        self._border_style = style
        self._box_builder = BoxBuilder(
            self._renderer, border_style=style,
        )
        self._panel_builder = PanelBuilder(
            self._renderer, self._console, style, self._normal_mode,
        )
        return self

    def refresh_size(self) -> ConsoleUI:
        """刷新终端尺寸"""
        self._renderer.update_reference_width()
        return self

    def reset_lines(self) -> ConsoleUI:
        """重置行计数"""
        self._line_count = 0
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 核心输出方法（调用链）
    # ══════════════════════════════════════════════════════════════════════════

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

    def stream(
        self,
        text: str,
        delay: float = 0.02,
        newline: bool = True,
    ) -> ConsoleUI:
        """同步流式输出（逐字符渐变）"""
        self._stream_writer.reset()
        lines = self._stream_writer.write_text(text, delay)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        self._log_writer.write(text)
        return self

    async def stream_async(
        self,
        text: str,
        delay: float = 0.02,
        newline: bool = True,
    ) -> ConsoleUI:
        """异步流式输出（逐字符渐变）"""
        self._stream_writer.reset()
        lines = await self._stream_writer.write_text_async(text, delay)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        self._log_writer.write(text)
        return self

    def stream_iter(
        self,
        iterable: Iterator[str],
        delay: float = 0.0,
        newline: bool = True,
    ) -> ConsoleUI:
        """从迭代器流式输出（适用于 LLM 响应等）"""
        self._stream_writer.reset()
        lines = 0
        for chunk in iterable:
            for char in chunk:
                if char == "\n":
                    _write_flush(f"{ANSI_RESET}\n")
                    lines += 1
                    self._stream_writer._char_index = 0
                else:
                    self._stream_writer.write_char(char, 100)
                if delay > 0:
                    time.sleep(delay)
            sys.stdout.flush()

        _write_flush(ANSI_RESET)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        return self

    async def stream_aiter(
        self,
        iterable: AsyncIterator[str],
        delay: float = 0.0,
        newline: bool = True,
    ) -> ConsoleUI:
        """从异步迭代器流式输出"""
        self._stream_writer.reset()
        lines = 0
        async for chunk in iterable:
            for char in chunk:
                if char == "\n":
                    _write_flush(f"{ANSI_RESET}\n")
                    lines += 1
                    self._stream_writer._char_index = 0
                else:
                    self._stream_writer.write_char(char, 100)
                if delay > 0:
                    await asyncio.sleep(delay)
            sys.stdout.flush()

        _write_flush(ANSI_RESET)
        if newline:
            _write_flush("\n")
            lines += 1
        self._line_count += lines
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 行操作（调用链）
    # ══════════════════════════════════════════════════════════════════════════

    def delete_lines(self, count: int = 1) -> ConsoleUI:
        """删除指定行数"""
        if count <= 0:
            return self
        _write_flush((ANSI_MOVE_UP + ANSI_CLEAR_LINE) * count)
        self._line_count = max(0, self._line_count - count)
        return self

    def clear_output(self) -> ConsoleUI:
        """清除所有已跟踪的输出"""
        return self.delete_lines(self._line_count)

    def clear_line(self) -> ConsoleUI:
        """清除当前行"""
        _write_flush(ANSI_CLEAR_LINE)
        return self

    def clear_screen(self) -> ConsoleUI:
        """清屏"""
        _write_flush(ANSI_CLEAR_SCREEN)
        self._line_count = 0
        return self

    # ══════════════════════════════════════════════════════════════════════════
    # 输入方法
    # ══════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 便捷工厂函数
# ══════════════════════════════════════════════════════════════════════════════


def create_ui(
    theme: Optional[GradientTheme] = None,
    log_path: Optional[str] = None,
    char_map: Optional[Dict[str, List[str]]] = None,
    normal_mode: bool = False,
    border_style: BorderStyle = BorderStyle.ROUNDED,
    log_writers: Optional[Sequence[LogWriter]] = None,
) -> ConsoleUI:
    """
    创建 ConsoleUI 实例的便捷工厂函数

    参数：
      theme: 渐变主题
      log_path: 日志文件路径
      char_map: ASCII 艺术字符映射
      normal_mode: 是否为普通模式（无颜色）
      border_style: 默认边框样式
      log_writers: 额外的日志写入器列表
    """
    writers: List[LogWriter] = []
    if log_path:
        writers.append(FileLogWriter(log_path))
    if log_writers:
        writers.extend(log_writers)

    log_writer: LogWriter
    if not writers:
        log_writer = NullLogWriter()
    elif len(writers) == 1:
        log_writer = writers[0]
    else:
        log_writer = MultiLogWriter(*writers)

    return ConsoleUI(
        theme=theme,
        log_writer=log_writer,
        char_map=char_map,
        normal_mode=normal_mode,
        border_style=border_style,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # 主类
    "ConsoleUI",
    # 工厂函数
    "create_ui",
    # 枚举
    "FontStyle",
    "Alignment",
    "BorderStyle",
    "SpinnerStyle",
    # 数据类
    "GradientTheme",
    "BorderChars",
    "SpinnerFrames",
    "SelectionResult",
    "TreeNode",
    # 渲染器
    "GradientRenderer",
    # 组件
    "StreamWriter",
    "AsyncInput",
    "BoxBuilder",
    "AsciiArtBuilder",
    "TableBuilder",
    "PanelBuilder",
    "ProgressBar",
    "AsyncProgressBar",
    "Spinner",
    "Divider",
    "Timer",
    "Notification",
    "KeyValueList",
    "MultiLineInput",
    "Pager",
    "Countdown",
    "ColumnLayout",
    "TreeView",
    "InteractiveSelector",
    "ConfirmDialog",
    # 日志
    "LogWriter",
    "FileLogWriter",
    "NullLogWriter",
    "MultiLogWriter",
    "CallbackLogWriter",
    # 工具
    "TextUtils",
    # 类型
    "RGB",
]

