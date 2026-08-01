"""Tests for console UI bridge helpers."""

from __future__ import annotations

from echotools.media.console import (
    DEFAULT_THEME_NAME,
    RichCLI,
    get_theme_palette,
    get_theme_preset,
    list_theme_names,
    normalize_theme_name,
    render_gradient_banner,
    render_text,
    render_text_lines,
    truncate_ansi,
)


class TestRenderTextLines:
    def test_render_text_basic(self) -> None:
        lines = render_text_lines("AB")
        assert len(lines) == 6
        assert all(isinstance(line, str) for line in lines)
        assert any("█" in line or "╗" in line for line in lines)

    def test_render_text_alias(self) -> None:
        assert render_text("A") == render_text_lines("A")


class TestRenderGradientBanner:
    def test_render_gradient_banner(self) -> None:
        lines = render_text_lines("HI")
        banner = render_gradient_banner(lines, theme_name="forest")
        assert isinstance(banner, str)
        assert len(banner) > 0


class TestThemes:
    def test_default_theme(self) -> None:
        assert DEFAULT_THEME_NAME == "ocean"

    def test_legacy_blue_alias(self) -> None:
        assert normalize_theme_name("blue") == "ocean"

    def test_unknown_theme_falls_back(self) -> None:
        assert normalize_theme_name("not-a-theme") == "ocean"

    def test_theme_diversity(self) -> None:
        names = list_theme_names()
        assert {"ocean", "forest", "sunset", "violet", "rose", "slate", "cyan"}.issubset(set(names))
        assert get_theme_palette("forest") != get_theme_palette("sunset")

    def test_rich_cli_accepts_theme(self) -> None:
        cli = RichCLI(theme_name="violet")
        assert cli.theme_name == "violet"


class TestTruncateAnsi:
    def test_truncate_ansi_long(self) -> None:
        result = truncate_ansi("hello world", 5)
        assert "…" in result
