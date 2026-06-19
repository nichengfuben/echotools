"""Terminal session management -- local shells and SSH."""
from __future__ import annotations

from .local import LocalTerminal
from .session import TerminalCallback, TerminalSession
from .ssh import SSHTerminal

__all__ = ["TerminalSession", "TerminalCallback", "LocalTerminal", "SSHTerminal"]
