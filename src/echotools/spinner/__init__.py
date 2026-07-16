from __future__ import annotations

"""echotools.spinner：终端 Spinner 动画组件。

支持暂停/恢复、主题切换(rainbow/static/gradient)、动态消息更新、终态展示。
"""

from echotools.spinner.spinner import (
    Clock,
    KeyListener,
    Spinner,
    get_default_characters,
    hue_to_rgb,
    to_rgb_color_str,
)

__all__ = [
    "Clock",
    "KeyListener",
    "Spinner",
    "get_default_characters",
    "hue_to_rgb",
    "to_rgb_color_str",
]
