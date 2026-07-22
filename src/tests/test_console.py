from __future__ import annotations

"""ConsoleUI import tests."""


def test_console_package_import() -> None:
    from echotools.media.console import (
        BorderStyle,
        Clock,
        ConsoleUI,
        FontStyle,
        GradientTheme,
        Spinner,
        char_map,
    )

    assert char_map
    assert ConsoleUI is not None
    assert Spinner is not None
    assert Clock is not None
    assert BorderStyle.ROUNDED is not None


def test_console_compat_alias() -> None:
    from echotools.console import ConsoleUI, char_map

    assert ConsoleUI is not None
    assert char_map
