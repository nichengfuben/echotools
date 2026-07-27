"""Console UI enums, constants, and data types."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar, Dict, Final, Tuple

RGB = Tuple[int, int, int]
IS_WINDOWS: Final[bool] = sys.platform == "win32"
IS_MACOS: Final[bool] = sys.platform == "darwin"
IS_LINUX: Final[bool] = sys.platform.startswith("linux")

ANSI_RESET: Final[str] = "\033[0m"
ANSI_HIDE_CURSOR: Final[str] = "\033[?25l"
ANSI_SHOW_CURSOR: Final[str] = "\033[?25h"
ANSI_CLEAR_LINE: Final[str] = "\r\033[K"
ANSI_MOVE_UP: Final[str] = "\033[F"
ANSI_CLEAR_SCREEN: Final[str] = "\033[2J\033[H"
ANSI_BOLD: Final[str] = "\033[1m"

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

