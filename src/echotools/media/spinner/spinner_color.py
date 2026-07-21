from __future__ import annotations

"""终端 Spinner 动画组件。

支持暂停/恢复(空格键)、主题切换(rainbow/static/gradient)、
动态消息更新(update_message)、终态展示(stop 时可显示成功/失败图标)。
"""

import math
import os
import platform
from typing import Callable, Dict, List, Tuple

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
    sector = int(h / 60) % 6
    rgb = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][sector]
    return (
        round((rgb[0] + m) * 255),
        round((rgb[1] + m) * 255),
        round((rgb[2] + m) * 255),
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



