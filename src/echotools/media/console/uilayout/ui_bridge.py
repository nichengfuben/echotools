"""Sync bridge helpers for ConsoleUI (select/confirm, themes, config coercion)."""

from __future__ import annotations

import asyncio
import io
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from echotools.media.console import char_map, create_ui
from echotools.media.console.uicore.ui_platform import _get_backend
from echotools.media.console.uicore.ui_text import GradientRenderer, TextUtils
from echotools.media.console.uicore.ui_types import GradientTheme
from echotools.media.console.uiwidgets.ui_select import SelectionResult
from echotools.media.console.uiwidgets.ui_themes import (
    DEFAULT_THEME_NAME,
    get_gradient_theme,
    get_theme_palette,
    get_theme_preset,
    normalize_theme_name,
)

__all__ = [
    "DEFAULT_THEME_NAME",
    "coerce_config_set_value",
    "coerce_config_value",
    "create_themed_ui",
    "ensure_windows_console",
    "flatten_config_fields",
    "flatten_model_fields",
    "get_utf8_stdout",
    "normalize_theme_name",
    "render_bar",
    "render_gradient_banner",
    "render_text",
    "render_text_lines",
    "run_confirm",
    "run_select",
    "truncate_ansi",
]


def ensure_windows_console() -> None:
    if sys.platform != "win32":
        return
    try:
        _get_backend().init_console()
    except Exception:
        pass


def get_utf8_stdout():
    if sys.platform != "win32":
        return sys.stdout
    if "pytest" in sys.modules:
        return sys.stdout
    try:
        return io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )
    except (AttributeError, OSError):
        return sys.stdout


def create_themed_ui(
    *,
    theme_name: str | None = None,
    theme: Optional[GradientTheme] = None,
    char_map_data: Optional[Dict[str, List[str]]] = None,
    normal_mode: bool = False,
):
    ensure_windows_console()
    active_theme = theme or get_gradient_theme(theme_name)
    ui = create_ui(
        theme=active_theme,
        char_map=char_map_data or char_map,
        normal_mode=normal_mode,
    )
    if sys.platform == "win32" and not normal_mode and "pytest" not in sys.modules:
        ui._console.file = get_utf8_stdout()  # type: ignore[attr-defined]
        ui._console._force_terminal = True  # type: ignore[attr-defined]
    return ui


def run_select(
    ui,
    title: str,
    options: Sequence[str],
    default_index: int = 0,
) -> SelectionResult:
    return asyncio.run(ui.select(title, list(options), default_index))


def run_confirm(ui, message: str, default: bool = True) -> bool:
    return asyncio.run(ui.confirm(message, default))


def render_text_lines(text: str, glyph_map: Optional[Dict[str, List[str]]] = None) -> list[str]:
    mapping = glyph_map or char_map
    lines = ["", "", "", "", "", ""]
    for ch in text:
        glyph = mapping.get(ch) or mapping.get(ch.upper()) or mapping.get(ch.lower())
        if glyph is not None:
            for i in range(6):
                lines[i] += glyph[i]
    return lines


render_text = render_text_lines


def render_gradient_banner(
    lines: list[str],
    *,
    theme_name: str | None = None,
    palette: Optional[List[Tuple[int, int, int]]] = None,
    theme: Optional[GradientTheme] = None,
) -> str:
    if not lines:
        return ""
    if theme is not None:
        active_theme = theme
    elif palette:
        active_theme = GradientTheme(
            primary_start=palette[0],
            primary_end=palette[-1],
            border_start=palette[0],
            border_end=palette[-1],
        )
    else:
        active_theme = get_theme_preset(theme_name).gradient
    renderer = GradientRenderer(active_theme)
    banner = renderer.render_banner("\n".join(lines), use_border_colors=True, row_offset=0)
    return str(banner)


def flatten_model_fields(
    config: Any,
    section_names: Sequence[str] = ("patch", "ui", "paths", "persistence"),
) -> list[tuple[str, str]]:
    flat: list[tuple[str, str]] = []
    for section_name in section_names:
        section = getattr(config, section_name, None)
        if section is None:
            continue
        if hasattr(type(section), "model_fields"):
            fields = type(section).model_fields
        elif hasattr(section, "__fields__"):
            fields = section.__fields__
        else:
            continue
        for field_name in fields:
            dot_path = f"{section_name}.{field_name}"
            current = getattr(section, field_name, None)
            flat.append((dot_path, str(current)))
    return flat


flatten_config_fields = flatten_model_fields


def coerce_config_value(current_value: str, new_value_str: str) -> Any:
    if current_value in ("True", "False"):
        return new_value_str.lower() in ("true", "1", "yes", "是")
    if current_value.isdigit():
        try:
            return int(new_value_str)
        except ValueError:
            return new_value_str
    if current_value == "None":
        return None if new_value_str in ("", "None", "null") else new_value_str
    return new_value_str


def coerce_config_set_value(current: object, value: str) -> object:
    if isinstance(current, bool):
        return value.lower() in ("true", "1", "yes", "是")
    if isinstance(current, int):
        return int(value)
    if current is None and value in ("None", "null", ""):
        return None
    return value


def render_bar(pct: Any, width: int = 30) -> str:
    try:
        p = max(0.0, min(100.0, float(pct)))
    except Exception:
        return "[" + ("░" * width) + "]"
    filled = int(width * p / 100.0)
    return "[" + ("█" * filled) + ("░" * (width - filled)) + "]"


def truncate_ansi(text: str, width: int) -> str:
    if TextUtils.display_width(text) <= width:
        return text
    plain = TextUtils.strip_ansi(text)
    trimmed = TextUtils.truncate(plain, max(0, width - 1))
    return trimmed + "…\033[0m"
