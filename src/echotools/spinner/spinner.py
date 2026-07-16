from __future__ import annotations

"""终端 Spinner 动画组件。

支持暂停/恢复(空格键)、主题切换(rainbow/static/gradient)、
动态消息更新(update_message)、终态展示(stop 时可显示成功/失败图标)。
"""

import math
import os
import platform
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

SPEED_MULTIPLIER = 1.5
FRAME_INTERVAL_MS = 16


def get_default_characters() -> List[str]:
    term = os.environ.get("TERM", "")
    if term == "xterm-ghostty":
        return ["·", "✢", "✳", "✶", "✻", "*"]
    if platform.system() == "Darwin":
        return ["·", "✢", "✳", "✶", "✻", "✽"]
    return ["·", "✢", "*", "✶", "✻", "✽"]


def hue_to_rgb(hue: float) -> Tuple[int, int, int]:
    h = ((hue % 360) + 360) % 360
    s = 0.7
    lightness = 0.6
    c = (1 - abs(2 * lightness - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = lightness - c / 2
    r = g = b = 0.0
    if h < 60:
        r = c
        g = x
    elif h < 120:
        r = x
        g = c
    elif h < 180:
        g = c
        b = x
    elif h < 240:
        g = x
        b = c
    elif h < 300:
        r = x
        b = c
    else:
        r = c
        b = x
    return (
        round((r + m) * 255),
        round((g + m) * 255),
        round((b + m) * 255),
    )


def to_rgb_color_str(color: Tuple[int, int, int]) -> str:
    return f"\033[38;2;{color[0]};{color[1]};{color[2]}m"


THEME_STATIC_COLOR: Tuple[int, int, int] = (0, 200, 255)

GRADIENT_STOPS: List[Tuple[int, int, int]] = [
    (255, 60, 120),
    (255, 200, 0),
    (0, 220, 160),
    (0, 140, 255),
]


def _theme_rainbow(time_ms: float) -> Tuple[int, int, int]:
    hue = (time_ms / (20 / SPEED_MULTIPLIER)) % 360
    return hue_to_rgb(hue)


def _theme_static(time_ms: float) -> Tuple[int, int, int]:
    return THEME_STATIC_COLOR


def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def _theme_gradient(time_ms: float) -> Tuple[int, int, int]:
    cycle_ms = 4000 / SPEED_MULTIPLIER
    n = len(GRADIENT_STOPS)
    pos = ((time_ms % cycle_ms) / cycle_ms) * n
    idx = int(math.floor(pos)) % n
    next_idx = (idx + 1) % n
    t = pos - math.floor(pos)
    c1 = GRADIENT_STOPS[idx]
    c2 = GRADIENT_STOPS[next_idx]
    return (
        _lerp(c1[0], c2[0], t),
        _lerp(c1[1], c2[1], t),
        _lerp(c1[2], c2[2], t),
    )


THEMES: Dict[str, Callable[[float], Tuple[int, int, int]]] = {
    "rainbow": _theme_rainbow,
    "static": _theme_static,
    "gradient": _theme_gradient,
}

STATUS_ICONS: Dict[str, Tuple[str, Tuple[int, int, int]]] = {
    "success": ("✓", (60, 220, 100)),
    "error": ("✗", (230, 60, 60)),
}


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

        def unsubscribe() -> None:
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

    def set_tick_interval(self, ms: int) -> None:
        with self._lock:
            new_interval = ms / SPEED_MULTIPLIER
            if new_interval == self._current_tick_interval_ms:
                return
            self._current_tick_interval_ms = new_interval


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


class KeyListener:
    """后台线程监听按键；仅识别空格键触发回调，Windows/POSIX 均支持。"""

    def __init__(self, on_space: Callable[[], None]):
        self._on_space = on_space
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        if platform.system() == "Windows":
            self._run_windows()
        else:
            self._run_posix()

    def _run_windows(self) -> None:
        try:
            import msvcrt
        except ImportError:
            return
        while not self._stop_event.is_set():
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == " ":
                    self._on_space()
            else:
                time.sleep(0.03)

    def _run_posix(self) -> None:
        try:
            import select
            import termios
            import tty
        except ImportError:
            return
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not self._stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.03)
                if ready:
                    ch = sys.stdin.read(1)
                    if ch == " ":
                        self._on_space()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


DEFAULT_CHARACTERS = get_default_characters()
SPINNER_FRAMES = DEFAULT_CHARACTERS + list(reversed(DEFAULT_CHARACTERS))


class Spinner:
    def __init__(
        self,
        clock: Clock,
        mode: str = "working",
        reduced_motion: bool = False,
        columns: int = 80,
        message: str = "Working on your request",
        theme: str = "rainbow",
        pausable: bool = False,
    ):
        self._clock = clock
        self._mode = mode
        self._reduced_motion = reduced_motion
        self._columns = columns
        self._message = message
        self._message_lock = threading.Lock()
        self._anim_frame = AnimationFrameState(clock, interval_ms=120)
        self._running = False
        self._frame_index = 0
        self._time_ms: float = 0.0

        self.set_theme(theme)

        self._paused = False
        self._pause_lock = threading.Lock()
        self._pause_started_at: float = 0.0
        self._paused_elapsed: float = 0.0

        self._key_listener: Optional[KeyListener] = None
        if pausable:
            self._key_listener = KeyListener(self.toggle_pause)

        self._final_char: Optional[str] = None
        self._final_color: Optional[Tuple[int, int, int]] = None

    def set_theme(self, theme: str) -> None:
        if theme not in THEMES:
            raise ValueError(f"未知主题: {theme}. 可选: {', '.join(THEMES.keys())}")
        self._theme = theme
        self._theme_fn = THEMES[theme]

    def update_message(self, message: str) -> None:
        with self._message_lock:
            self._message = message
        if self._running:
            self._render_frame()

    def toggle_pause(self) -> None:
        with self._pause_lock:
            if self._paused:
                self._paused = False
                self._paused_elapsed += time.perf_counter() * 1000 - self._pause_started_at
            else:
                self._paused = True
                self._pause_started_at = time.perf_counter() * 1000

    def is_paused(self) -> bool:
        with self._pause_lock:
            return self._paused

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._anim_frame.start()
        if self._key_listener is not None:
            self._key_listener.start()
        self._run_loop()

    def stop(self, status: Optional[str] = None) -> None:
        self._running = False
        self._anim_frame.stop()
        if self._key_listener is not None:
            self._key_listener.stop()
        if status is not None:
            if status not in STATUS_ICONS:
                raise ValueError(f"未知终态: {status}. 可选: {', '.join(STATUS_ICONS.keys())}")
            self._final_char, self._final_color = STATUS_ICONS[status]
            self._render(self._final_char, self._final_color)
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _run_loop(self) -> None:
        while self._running:
            updated = self._anim_frame.wait_for_update(timeout=0.050)
            if updated:
                self._anim_frame.clear_event()
                if self.is_paused():
                    continue
                self._time_ms = self._anim_frame.get_time()
                self._render_frame()

    def _render_frame(self) -> None:
        if not self._running:
            return

        frame_interval = 120 / SPEED_MULTIPLIER
        if not self._reduced_motion:
            self._frame_index = int(math.floor(self._time_ms / frame_interval)) % len(SPINNER_FRAMES)
        else:
            self._frame_index = 0
        char = SPINNER_FRAMES[self._frame_index]

        color = self._theme_fn(self._time_ms)

        self._render(char, color)

    def _render(self, char: str, color: Tuple[int, int, int]) -> None:
        reset = "\033[0m"
        color_code = to_rgb_color_str(color)
        with self._message_lock:
            message = self._message
        suffix = " [已暂停]" if self.is_paused() else ""
        output = f"{color_code}{char}{reset} {color_code}{message}{suffix}{reset}"
        padding = max(0, self._columns - len(output) - 1)
        output = f"\r{output}{' ' * padding}"
        sys.stdout.write(output)
        sys.stdout.flush()
