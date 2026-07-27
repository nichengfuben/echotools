"""ConsoleUI main class."""
from __future__ import annotations

from echotools.media.console.uicore.mixins import (
    _ConsoleUIBase,
    _ConsoleUICmdsMixin,
    _ConsoleUIInteractMixin,
    _ConsoleUIOutputMixin,
    _ConsoleUIStreamMixin,
)


class ConsoleUI(
    _ConsoleUIStreamMixin,
    _ConsoleUICmdsMixin,
    _ConsoleUIOutputMixin,
    _ConsoleUIInteractMixin,
    _ConsoleUIBase,
):
    """控制台UI主类 - 高性能异步控制台UI框架"""
