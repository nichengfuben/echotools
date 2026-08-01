"""Named gradient + Rich theme presets for ConsoleUI apps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from echotools.media.console.uicore.ui_types import GradientTheme
from rich.theme import Theme

RGB = Tuple[int, int, int]

DEFAULT_THEME_NAME = "ocean"

_LEGACY_ALIASES = {"blue": "ocean", "default": "ocean"}


@dataclass(frozen=True)
class ThemePreset:
    """One selectable CLI theme: gradient colors + Rich markup styles."""

    name: str
    gradient: GradientTheme
    palette: Tuple[RGB, ...]
    accent: str
    border: str
    header: str
    column: str
    menu_bg: str


def _gradient(
    primary_start: RGB,
    primary_end: RGB,
    border_start: RGB,
    border_end: RGB,
    accent_start: RGB,
    accent_end: RGB,
) -> GradientTheme:
    return GradientTheme(
        primary_start=primary_start,
        primary_end=primary_end,
        border_start=border_start,
        border_end=border_end,
        accent_start=accent_start,
        accent_end=accent_end,
        success=(34, 197, 94),
        warning=(234, 179, 8),
        error=(239, 68, 68),
        info=(6, 182, 212),
        muted=(100, 116, 139),
    )


def _rich_theme(preset: ThemePreset) -> Theme:
    accent = preset.accent
    border = preset.border
    header = preset.header
    return Theme(
        {
            "info": "cyan",
            "warning": "yellow",
            "error": "bold red",
            "success": "bold green",
            "header": header,
            "header.title": f"bold {accent} on dark_{border}",
            "menu.selected": f"bold white on {preset.menu_bg}",
            "menu.unselected": f"dim {border}",
            "prompt": "bold cyan",
            "accent": accent,
            "muted": f"dim {border}",
            "border": border,
            "table.header": f"bold white on {border}",
            "table.row": border,
            "table.footer": header,
        }
    )


def _preset(
    name: str,
    primary_start: RGB,
    primary_end: RGB,
    border_start: RGB,
    border_end: RGB,
    accent_start: RGB,
    accent_end: RGB,
    palette: Sequence[RGB],
    accent: str,
    border: str,
    header: str,
    column: str,
    menu_bg: str,
) -> ThemePreset:
    return ThemePreset(
        name=name,
        gradient=_gradient(
            primary_start, primary_end, border_start, border_end, accent_start, accent_end
        ),
        palette=tuple(palette),
        accent=accent,
        border=border,
        header=header,
        column=column,
        menu_bg=menu_bg,
    )


THEME_PRESETS: Dict[str, ThemePreset] = {
    "ocean": _preset(
        "ocean",
        (37, 99, 235),
        (96, 165, 250),
        (30, 58, 95),
        (37, 99, 235),
        (59, 130, 246),
        (147, 197, 253),
        [(20, 80, 255), (40, 120, 255), (60, 160, 255), (80, 200, 255), (100, 230, 255)],
        "bright_blue",
        "blue",
        "bold bright_blue",
        "blue",
        "blue",
    ),
    "forest": _preset(
        "forest",
        (22, 101, 52),
        (74, 222, 128),
        (20, 83, 45),
        (34, 197, 94),
        (34, 197, 94),
        (134, 239, 172),
        [(10, 70, 40), (20, 110, 60), (34, 160, 80), (56, 190, 110), (90, 220, 140)],
        "bright_green",
        "green",
        "bold bright_green",
        "green",
        "green",
    ),
    "sunset": _preset(
        "sunset",
        (194, 65, 12),
        (251, 146, 60),
        (124, 45, 18),
        (234, 88, 12),
        (249, 115, 22),
        (253, 186, 116),
        [(120, 40, 10), (170, 60, 15), (210, 90, 25), (240, 130, 50), (255, 180, 90)],
        "bright_red",
        "red",
        "bold bright_red",
        "red",
        "red3",
    ),
    "violet": _preset(
        "violet",
        (109, 40, 217),
        (167, 139, 250),
        (76, 29, 149),
        (124, 58, 237),
        (139, 92, 246),
        (196, 181, 253),
        [(70, 20, 140), (90, 40, 180), (120, 60, 210), (150, 90, 230), (180, 130, 250)],
        "bright_magenta",
        "magenta",
        "bold bright_magenta",
        "magenta",
        "purple",
    ),
    "rose": _preset(
        "rose",
        (190, 24, 93),
        (244, 114, 182),
        (131, 24, 67),
        (219, 39, 119),
        (236, 72, 153),
        (249, 168, 212),
        [(120, 10, 50), (160, 30, 70), (200, 50, 95), (230, 80, 130), (250, 130, 180)],
        "bright_red",
        "deep_pink3",
        "bold deep_pink3",
        "deep_pink3",
        "deep_pink3",
    ),
    "slate": _preset(
        "slate",
        (51, 65, 85),
        (148, 163, 184),
        (30, 41, 59),
        (71, 85, 105),
        (100, 116, 139),
        (203, 213, 225),
        [(30, 35, 45), (45, 55, 70), (70, 80, 95), (110, 120, 135), (150, 160, 175)],
        "bright_white",
        "grey50",
        "bold bright_white",
        "grey62",
        "grey37",
    ),
    "cyan": _preset(
        "cyan",
        (14, 116, 144),
        (34, 211, 238),
        (21, 94, 117),
        (8, 145, 178),
        (6, 182, 212),
        (103, 232, 249),
        [(0, 80, 100), (0, 110, 130), (0, 145, 165), (20, 180, 200), (80, 220, 240)],
        "bright_cyan",
        "cyan",
        "bold bright_cyan",
        "cyan",
        "cyan",
    ),
}


def normalize_theme_name(name: str | None) -> str:
    if not name:
        return DEFAULT_THEME_NAME
    key = name.strip().lower()
    key = _LEGACY_ALIASES.get(key, key)
    return key if key in THEME_PRESETS else DEFAULT_THEME_NAME


def get_theme_preset(name: str | None = None) -> ThemePreset:
    return THEME_PRESETS[normalize_theme_name(name)]


def list_theme_names() -> List[str]:
    return list(THEME_PRESETS.keys())


def get_gradient_theme(name: str | None = None) -> GradientTheme:
    return get_theme_preset(name).gradient


def get_theme_palette(name: str | None = None) -> Tuple[RGB, ...]:
    return get_theme_preset(name).palette


def get_rich_theme(name: str | None = None) -> Theme:
    return _rich_theme(get_theme_preset(name))
