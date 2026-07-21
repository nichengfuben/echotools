from __future__ import annotations

"""Local terminal session -- Windows (asyncio subprocess) and Unix (pty).

Supports process keep-alive: the shell process survives client
disconnection (``detach()``).  Output produced while detached is
buffered and delivered when a new client attaches (``attach()``).

Features (same as T3 Code):
- Shell fallback chain with retryable error detection
- Output sanitization for history
- Subprocess monitoring
- History management (5000 lines max)
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Optional

from ..session import TerminalCallback, TerminalSession

logger = logging.getLogger(__name__)

# ConPTY availability (Windows only, requires pywinpty).
try:
    from ..conpty import ConPTYHandle

    _HAS_CONPTY = True
except ImportError:
    ConPTYHandle = None  # type: ignore[assignment, misc]
    _HAS_CONPTY = False

# Shell fallback candidates (same as T3 Code)
_WINDOWS_SHELL_CANDIDATES = [
    "pwsh.exe",           # PowerShell Core
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",  # PowerShell
    "powershell.exe",     # PowerShell (PATH)
    None,                 # ComSpec (from environment)
    "cmd.exe",            # Command Prompt
]

_POSIX_SHELL_CANDIDATES = [
    None,  # $SHELL (from environment)
    "/bin/zsh",
    "/bin/bash",
    "/bin/sh",
    "zsh",  # PATH lookup
    "bash",
    "sh",
]


def _pid_alive(pid: int) -> bool:
    """Check whether a PID is still running (cross-platform)."""
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            # On Windows, os.kill with signal 0 raises OSError if the
            # process does not exist.
            os.kill(pid, 0)
            return True
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


from .proc import LocalTerminalProcMixin
from .unix import LocalTerminalUnixMixin
from .win import LocalTerminalWindowsMixin


class LocalTerminal(
    LocalTerminalWindowsMixin,
    LocalTerminalUnixMixin,
    LocalTerminalProcMixin,
    TerminalSession,
):
    """Terminal session backed by a local shell process.

    On **Windows** the preferred implementation uses ConPTY (via
    *pywinpty*) to allocate a real pseudo-console for ``cmd.exe``.  This
    enables ANSI escape sequences, ``cls``, ``color``, resize, and
    interactive features like Tab completion.  If *pywinpty* is not
    installed the session falls back to ``asyncio.create_subprocess_exec``
    with plain pipes.

    On **Unix** a pseudo-terminal is allocated via ``pty.openpty()`` and a
    shell process is started with ``subprocess.Popen``.  Window-size changes
    are propagated through ``ioctl(TIOCSWINSZ)``.

    Process keep-alive
    ------------------
    * ``detach()`` -- client disconnects; process keeps running, output
      is buffered.
    * ``attach(callback)`` -- new client connects; buffered output is
      flushed, then live output streams.
    * ``kill()`` -- user explicitly closes the tab; process is terminated.
    * ``close()`` -- backward-compatible alias for ``kill()``.
    """

    def __init__(
        self,
        session_id: str,
        callback: Optional[TerminalCallback] = None,
    ) -> None:
        super().__init__(session_id=session_id, kind="local", callback=callback)

        self._conpty: Optional["ConPTYHandle"] = None

        self._async_process: Optional[asyncio.subprocess.Process] = None
        self._orig_handler = None

        self._process: Optional[subprocess.Popen[bytes]] = None
        self._fd: Optional[int] = None  # pty master fd

        # Cached PID (set after start)
        self._pid: Optional[int] = None

    # Public interface

    async def start(self, cols: int = 80, rows: int = 24) -> bool:
        """Start a local shell process."""
        self.cols = cols
        self.rows = rows
        try:
            if sys.platform == "win32":
                return await self._start_windows(cols, rows)
            else:
                return await self._start_unix(cols, rows)
        except Exception as exc:
            await self._fire_error(f"Failed to start local terminal: {exc}")
            return False

    async def write(self, data: str) -> None:
        """Write input data to the terminal process."""
        if not data:
            return
        try:
            if sys.platform == "darwin" and self._needs_chunked_write(data):
                await self._write_chunked(data)
                return
            await self._write_raw(data)
        except Exception:
            logger.debug("write failed (session %s)", self.session_id, exc_info=True)

    @staticmethod
    def _needs_chunked_write(data: str) -> bool:
        if len(data.encode("utf-8")) <= 512:
            return False
        return "\n" in data or "\r" in data

    async def _write_chunked(self, data: str) -> None:
        """macOS cooked-mode PTY: chunk multiline paste to avoid ~1KB corruption."""
        encoded = data.encode("utf-8")
        chunk_size = 512
        for offset in range(0, len(encoded), chunk_size):
            piece = encoded[offset : offset + chunk_size].decode("utf-8", errors="replace")
            await self._write_raw(piece)
            if offset + chunk_size < len(encoded):
                await asyncio.sleep(0.005)

    async def _write_raw(self, data: str) -> None:
        if self._conpty is not None:
            await self._conpty.write(data)
        elif self._async_process is not None and self._async_process.stdin is not None:
            encoded = data.encode("utf-8")
            self._async_process.stdin.write(encoded)
            await self._async_process.stdin.drain()
        elif self._fd is not None:
            encoded = data.encode("utf-8")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, os.write, self._fd, encoded)
        elif self._process is not None and self._process.stdin is not None:
            encoded = data.encode("utf-8")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_stdin_sync, encoded)

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal.

        On ConPTY (Windows) and Unix (pty), the new size is propagated to
        the underlying pseudo-console.  On the Windows pipe fallback the
        call is a no-op (only updates the stored *cols*/*rows* attributes).
        """
        self.cols = cols
        self.rows = rows
        if self._conpty is not None:
            await self._conpty.resize(cols, rows)
        elif self._fd is not None:
            self._set_pty_size(cols, rows)

    async def kill(self) -> None:
        """Explicitly terminate the shell process and clean up resources."""
        self.alive = False
        self._callbacks.clear()
        self._callback = None
        await self._cancel_reader()
        await _cleanup_conpty(self)
        await _cleanup_pty_fd(self)
        await _cleanup_async_process(self)
        await _cleanup_sync_process(self)
        self._pid = None
        logger.debug("Session %s killed", self.session_id)

    async def close(self) -> None:
        """Terminate the session and clean up resources.

        Backward-compatible alias for :meth:`kill`.
        """
        await self.kill()

    # Process introspection

    @property
    def pid(self) -> Optional[int]:
        """PID of the underlying shell process."""
        if self._pid is not None:
            return self._pid
        # ConPTY
        if self._conpty is not None:
            return self._conpty.pid
        # Asyncio subprocess (pipe fallback)
        if self._async_process is not None:
            return self._async_process.pid
        if self._process is not None:
            return self._process.pid
        return None

    @property
    def is_alive(self) -> bool:
        """Whether the underlying shell process is still running."""
        if not self.alive:
            return False
        # Check ConPTY
        if self._conpty is not None:
            return self._conpty.is_alive
        # Check asyncio process
        if self._async_process is not None:
            return self._async_process.returncode is None
        # Check Unix process
        if self._process is not None:
            return self._process.poll() is None
        # Check cached PID
        if self._pid is not None:
            return _pid_alive(self._pid)
        return False


async def _cleanup_conpty(terminal: LocalTerminal) -> None:
    if terminal._conpty is None:
        return
    try:
        await terminal._conpty.close()
    except Exception:
        pass
    terminal._conpty = None


async def _cleanup_pty_fd(terminal: LocalTerminal) -> None:
    if terminal._fd is None:
        return
    try:
        os.close(terminal._fd)
    except Exception:
        pass
    terminal._fd = None


async def _cleanup_async_process(terminal: LocalTerminal) -> None:
    if terminal._async_process is None:
        return
    proc = terminal._async_process
    for pipe in (proc.stdin, proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except Exception:
                pass
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    terminal._async_process = None
    if terminal._orig_handler is not None:
        try:
            asyncio.get_event_loop().set_exception_handler(terminal._orig_handler)
        except Exception:
            pass
        terminal._orig_handler = None


async def _cleanup_sync_process(terminal: LocalTerminal) -> None:
    if terminal._process is None:
        return
    try:
        if sys.platform != "win32":
            try:
                os.killpg(os.getpgid(terminal._process.pid), signal.SIGTERM)
            except Exception:
                pass
        terminal._process.terminate()
        terminal._process.wait(timeout=3)
    except Exception:
        try:
            terminal._process.kill()
        except Exception:
            pass
