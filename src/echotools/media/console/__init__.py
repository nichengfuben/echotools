from __future__ import annotations

"""echotools.media.console：终端 ConsoleUI 框架。

渐变文本、圆角边框、ASCII 艺术字、表格/面板、异步输入与 Spinner。
依赖：rich、wcwidth（``pip install echotools[console]``）。
"""

from echotools.media.console.charmap import char_map
from echotools.media.console.spinner import Clock, Spinner
from echotools.media.console.ui import (
    Alignment,
    BorderStyle,
    ConsoleUI,
    FileLogWriter,
    FontStyle,
    GradientTheme,
    TextUtils,
    _get_backend,
    _normalize_key_event,
    create_ui,
)
from echotools.media.console.uilayout.ui_bridge import (
    DEFAULT_THEME_NAME,
    coerce_config_set_value,
    coerce_config_value,
    create_themed_ui,
    ensure_windows_console,
    flatten_config_fields,
    flatten_model_fields,
    get_utf8_stdout,
    normalize_theme_name,
    render_bar,
    render_gradient_banner,
    render_text,
    render_text_lines,
    run_confirm,
    run_select,
    truncate_ansi,
)
from echotools.media.console.uiwidgets.ui_richcli import RichCLI, get_console
from echotools.media.console.uiwidgets.ui_themes import (
    ThemePreset,
    get_gradient_theme,
    get_rich_theme,
    get_theme_palette,
    get_theme_preset,
    list_theme_names,
)

__all__ = [
    "Alignment",
    "BorderStyle",
    "Clock",
    "ConsoleUI",
    "DEFAULT_THEME_NAME",
    "FileLogWriter",
    "FontStyle",
    "GradientTheme",
    "RichCLI",
    "Spinner",
    "TextUtils",
    "ThemePreset",
    "char_map",
    "coerce_config_set_value",
    "coerce_config_value",
    "create_themed_ui",
    "create_ui",
    "ensure_windows_console",
    "flatten_config_fields",
    "flatten_model_fields",
    "get_console",
    "get_gradient_theme",
    "get_rich_theme",
    "get_theme_palette",
    "get_theme_preset",
    "get_utf8_stdout",
    "list_theme_names",
    "normalize_theme_name",
    "render_bar",
    "render_gradient_banner",
    "render_text",
    "render_text_lines",
    "run_confirm",
    "run_select",
    "truncate_ansi",
    "_get_backend",
    "_normalize_key_event",
]
