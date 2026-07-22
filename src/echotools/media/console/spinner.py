"""
Spinner 动画引擎 - 绿→蓝单向渐变版

关键修复：
- 用 ANSI 隐藏/显示光标 + \\r 覆盖同一行，确保动画在原地更新不换行
- stop() 后恢复光标并清除 spinner 行
"""

import sys
import time
import os
import platform
import math
import threading
from typing import List, Tuple, Dict, Callable, Optional

try:
    from wcwidth import wcswidth as _wcswidth
    def _display_width(s: str) -> int:
        w = _wcswidth(s)
        return w if w >= 0 else len(s)
except ImportError:
    def _display_width(s: str) -> int:
        return len(s)

# ═══════════════════════════════════════════════════════════════════════════
# 全局速度控制
# ═══════════════════════════════════════════════════════════════════════════
SPEED_MULTIPLIER = 1.5
FRAME_INTERVAL_MS = 16

# ═══════════════════════════════════════════════════════════════════════════
# ANSI 序列
# ═══════════════════════════════════════════════════════════════════════════
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_LINE  = "\033[2K"
RESET_COLOR = "\033[0m"


def _enable_win_ansi():
    """Windows 下启用 ANSI 转义支持。"""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
    # 备用：触发 os.system("") 也能激活
    os.system("")


_enable_win_ansi()

# ═══════════════════════════════════════════════════════════════════════════
# 字符集
# ═══════════════════════════════════════════════════════════════════════════

def get_default_characters() -> List[str]:
    term = os.environ.get('TERM', '')
    if term == 'xterm-ghostty':
        return ['·', '✢', '✳', '✶', '✻', '*']
    if platform.system() == 'Darwin':
        return ['·', '✢', '✳', '✶', '✻', '✽']
    else:
        return ['·', '✢', '*', '✶', '✻', '✽']


def to_rgb_color_str(color: Tuple[int, int, int]) -> str:
    return f"\033[38;2;{color[0]};{color[1]};{color[2]}m"


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


# ═══════════════════════════════════════════════════════════════════════════
# 主题：绿 → 蓝 单向渐变
# ═══════════════════════════════════════════════════════════════════════════

GREEN_START: Tuple[int, int, int] = (0, 230, 160)
BLUE_END:    Tuple[int, int, int] = (0, 160, 255)

TRANSITION_DURATION_MS = 1800 / SPEED_MULTIPLIER


def _theme_green_to_blue(elapsed_ms: float) -> Tuple[int, int, int]:
    t = min(max(elapsed_ms / TRANSITION_DURATION_MS, 0.0), 1.0)
    return (
        _lerp(GREEN_START[0], BLUE_END[0], t),
        _lerp(GREEN_START[1], BLUE_END[1], t),
        _lerp(GREEN_START[2], BLUE_END[2], t),
    )


THEMES: Dict[str, Callable[[float], Tuple[int, int, int]]] = {
    "green_blue": _theme_green_to_blue,
}


# ═══════════════════════════════════════════════════════════════════════════
# 时钟系统
# ═══════════════════════════════════════════════════════════════════════════


class Clock:
    def __init__(self, tick_interval_ms: int = FRAME_INTERVAL_MS):
        self._subscribers: Dict[Callable[[], None], bool] = {}
        self._current_tick_interval_ms = tick_interval_ms / SPEED_MULTIPLIER
        self._start_time: float = 0.0
        self._tick_time: float = 0.0
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _run_thread(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self._current_tick_interval_ms / 1000.0)
            if self._running and not self._stop_event.is_set():
                self._tick()

    def _tick(self) -> None:
        with self._lock:
            if not self._running:
                return
            now_ms = time.perf_counter() * 1000
            self._tick_time = now_ms - self._start_time
            subscribers = list(self._subscribers.keys())
        for on_change in subscribers:
            try:
                on_change()
            except Exception:
                pass

    def _update_interval(self) -> None:
        any_keep_alive = False
        with self._lock:
            any_keep_alive = any(self._subscribers.values())
        if any_keep_alive:
            with self._lock:
                if self._start_time == 0.0:
                    self._start_time = time.perf_counter() * 1000
                if not self._running:
                    self._running = True
                    self._stop_event.clear()
                    self._thread = threading.Thread(target=self._run_thread, daemon=True)
                    self._thread.start()
        else:
            with self._lock:
                if self._running:
                    self._running = False
                    self._stop_event.set()

    def subscribe(self, on_change: Callable[[], None], keep_alive: bool = False) -> Callable[[], None]:
        with self._lock:
            self._subscribers[on_change] = keep_alive
        self._update_interval()

        def unsubscribe():
            with self._lock:
                if on_change in self._subscribers:
                    del self._subscribers[on_change]
            self._update_interval()
        return unsubscribe

    def now(self) -> float:
        current_time = time.perf_counter() * 1000
        with self._lock:
            if self._start_time == 0.0:
                self._start_time = current_time
            if self._running and self._tick_time > 0:
                return self._tick_time
            return current_time - self._start_time


# ═══════════════════════════════════════════════════════════════════════════
# 动画帧状态
# ═══════════════════════════════════════════════════════════════════════════


class AnimationFrameState:
    def __init__(self, clock: Clock, interval_ms: float = 120):
        self._clock = clock
        self._interval_ms = interval_ms / SPEED_MULTIPLIER
        self._time: float = 0.0
        self._active = False
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._last_update: float = 0.0
        self._event = threading.Event()

    def _on_change(self) -> None:
        if not self._active:
            return
        now = self._clock.now()
        if now - self._last_update >= self._interval_ms:
            self._last_update = now
            self._time = now
            self._event.set()

    def start(self) -> None:
        if self._active:
            return
        self._active = True
        self._time = self._clock.now()
        self._last_update = self._time
        self._unsubscribe = self._clock.subscribe(self._on_change, keep_alive=True)

    def stop(self) -> None:
        self._active = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._event.set()

    def get_time(self) -> float:
        return self._time

    def wait_for_update(self, timeout: float = 0.001) -> bool:
        return self._event.wait(timeout)

    def clear_event(self) -> None:
        self._event.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Spinner 主类
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_CHARACTERS = get_default_characters()
SPINNER_FRAMES = DEFAULT_CHARACTERS + list(reversed(DEFAULT_CHARACTERS))


class Spinner:
    """
    彩色终端加载动画。

    核心行为：
    - start() 时隐藏光标，颜色从绿色开始
    - 后台线程用 \\r 回到行首覆盖输出，保证动画在同一行原地更新
    - stop() 时清除 spinner 行、恢复光标
    """

    def __init__(
        self,
        clock: Clock,
        reduced_motion: bool = False,
        columns: int = 80,
        message: str = "Working",
        theme: str = "green_blue",
    ):
        self._clock = clock
        self._reduced_motion = reduced_motion
        self._columns = columns
        self._message = message
        self._message_lock = threading.Lock()
        self._anim_frame = AnimationFrameState(clock, interval_ms=120)
        self._running = False
        self._frame_index = 0
        self._time_ms: float = 0.0
        self._start_offset_ms: float = 0.0

        # stdout 写锁：防止后台渲染线程和主线程(stop)竞争 stdout
        self._write_lock = threading.Lock()

        self.set_theme(theme)

    def set_theme(self, theme: str) -> None:
        if theme not in THEMES:
            theme = "green_blue"
        self._theme = theme
        self._theme_fn = THEMES[theme]

    def update_message(self, message: str) -> None:
        with self._message_lock:
            self._message = message

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._start_offset_ms = self._clock.now()
        # 隐藏光标，避免光标在 spinner 字符旁闪烁
        with self._write_lock:
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
        self._anim_frame.start()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def stop(self) -> None:
        was_running = self._running
        self._running = False
        self._anim_frame.stop()
        time.sleep(0.02)

        with self._write_lock:
            if was_running:
                sys.stdout.write(f"\r{CLEAR_LINE}{SHOW_CURSOR}")
                sys.stdout.flush()

    def _run_loop(self) -> None:
        while self._running:
            updated = self._anim_frame.wait_for_update(timeout=0.050)
            if updated:
                self._anim_frame.clear_event()
                if not self._running:
                    break
                self._time_ms = self._anim_frame.get_time()
                self._render_frame()

    def _render_frame(self) -> None:
        if not self._running:
            return

        elapsed = max(0.0, self._time_ms - self._start_offset_ms)

        frame_interval = 120 / SPEED_MULTIPLIER
        if not self._reduced_motion:
            self._frame_index = int(math.floor(elapsed / frame_interval)) % len(SPINNER_FRAMES)
        else:
            self._frame_index = 0
        char = SPINNER_FRAMES[self._frame_index]
        color = self._theme_fn(elapsed)

        color_code = to_rgb_color_str(color)
        with self._message_lock:
            message = self._message
        visible_len = _display_width(char) + 1 + _display_width(message)
        padding = max(0, self._columns - visible_len)
        # 关键：\r 回到行首，CLEAR_LINE 清除残留，不写 \n
        line = f"\r{CLEAR_LINE}{color_code}{char}{RESET_COLOR} {color_code}{message}{RESET_COLOR}{' ' * padding}"

        with self._write_lock:
            if self._running:  # 二次检查，防止 stop 已经调了
                sys.stdout.write(line)
                sys.stdout.flush()
