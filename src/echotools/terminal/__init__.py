"""Terminal session management -- local shells and SSH.

Features (same as T3 Code):
- Shell fallback chain with retryable error detection
- Output sanitization for history
- Subprocess monitoring
- History management (5000 lines max)
- Multi-client attachment with offline buffering
"""
from __future__ import annotations

from .local import LocalTerminal
from .sanitize import sanitize_terminal_history_chunk
from .session import (
    MAX_HISTORY_LINES,
    MAX_OFFLINE_BUFFER_BYTES,
    TerminalCallback,
    TerminalSession,
)
from .ssh import SSHTerminal

__all__ = [
    "TerminalSession",
    "TerminalCallback",
    "LocalTerminal",
    "SSHTerminal",
    "MAX_OFFLINE_BUFFER_BYTES",
    "MAX_HISTORY_LINES",
    "sanitize_terminal_history_chunk",
]
