"""Shared typing aliases for ConsoleUI mixins."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from echotools.media.console.uicore.ui_console import ConsoleUI

__all__ = ["ConsoleUI"]
