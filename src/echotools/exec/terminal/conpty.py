from __future__ import annotations

"""ConPTY backend for Windows terminal sessions using pywinpty.

This module wraps ``winpty.PTY`` (from the *pywinpty* package) to provide
a real pseudo-console on Windows.  Compared to the legacy pipe-based
approach (``asyncio.create_subprocess_exec``), ConPTY enables:

* ``cls``, ``color``, ``title``, ``mode`` builtins
* ANSI escape sequences (colours, cursor, clear-screen)
* Prompt colouring (cmd.exe enables ANSI itself)
* Terminal resize propagation (cols/rows)
* Arrow-key history and Tab completion with visual feedback

The public :class:`ConPTYHandle` class exposes an async-friendly interface
that mirrors the Unix PTY helpers in ``local.py``.

If *pywinpty* is not installed, importing this module raises
``ImportError`` -- callers should catch that and fall back to the pipe
path.
"""

import asyncio
import logging
import os
from typing import Dict, Optional

from winpty import PTY

logger = logging.getLogger(__name__)


def _env_dict_to_winpty_str(env: Dict[str, str]) -> str:
    """Convert an environment dict to pywinpty's null-separated format.

    pywinpty expects ``"KEY=VALUE\\0KEY2=VALUE2\\0"`` (trailing null).
    """
    return "".join(f"{k}={v}\0" for k, v in env.items())


class ConPTYHandle:
    """Async-friendly wrapper around ``winpty.PTY``.

    Parameters
    ----------
    cols:
        Initial terminal width in columns.
    rows:
        Initial terminal height in rows.
    """

    def __init__(self, cols: int = 80, rows: int = 24) -> None:
        self._cols = cols
        self._rows = rows
        self._pty: Optional[PTY] = PTY(cols, rows)
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def spawn(
        self,
        cmd: str,
        cmdline: Optional[str] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Start the child process attached to this ConPTY.

        Parameters
        ----------
        cmd:
            Path or name of the application to launch (e.g. ``"cmd.exe"``).
        cmdline:
            Optional command-line arguments string.
        cwd:
            Working directory for the child.  ``None`` inherits the
            current process directory.
        env:
            Environment variables dict.  ``None`` inherits the current
            process environment.

        Returns
        -------
        bool
            ``True`` if the process started successfully.
        """
        if self._pty is None:
            raise RuntimeError("ConPTY handle is already closed")

        env_str: Optional[str] = None
        if env is not None:
            env_str = _env_dict_to_winpty_str(env)

        ok = self._pty.spawn(cmd, cmdline=cmdline, cwd=cwd, env=env_str)
        if not ok:
            logger.warning("ConPTY spawn returned False for %r", cmd)
        return ok

    async def close(self) -> None:
        """Kill child process and release ConPTY handles."""
        if self._closed:
            return
        self._closed = True

        if self._pty is not None:
            try:
                self._pty.cancel_io()
            except Exception:
                pass

            # Kill the child process if still alive.
            pid = None
            try:
                pid = self._pty.pid
            except Exception:
                pass

            if pid is not None:
                try:
                    os.kill(pid, 9)  # SIGKILL equivalent on Windows
                except Exception:
                    pass

            self._pty = None

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    async def read(self) -> Optional[str]:
        """Read output from the child process.

        Runs the blocking ``PTY.read(blocking=True)`` in a thread-pool
        executor so it does not stall the asyncio event loop.

        Returns
        -------
        str or None
            Output text, or ``None`` when the child has exited and no
            more data is available (EOF).
        """
        if self._pty is None or self._closed:
            return None

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, self._blocking_read)
            return data
        except Exception:
            logger.debug("ConPTY read error", exc_info=True)
            return None

    def _blocking_read(self) -> Optional[str]:
        """Synchronous blocking read -- runs inside an executor thread."""
        if self._pty is None:
            return None
        try:
            # Use blocking=True for efficiency: the thread sleeps inside
            # the native call instead of busy-polling from Python.
            text = self._pty.read(blocking=True)
            if text:
                return text
            # Empty string with blocking=True usually means EOF.
            return None
        except Exception:
            return None

    async def write(self, data: str) -> int:
        """Write input to the child process.

        Parameters
        ----------
        data:
            UTF-8 string to send to the terminal.

        Returns
        -------
        int
            Number of bytes written.
        """
        if self._pty is None or self._closed:
            return 0

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._pty.write, data)
        except Exception:
            logger.debug("ConPTY write error", exc_info=True)
            return 0

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the pseudo-console.

        Parameters
        ----------
        cols:
            New terminal width.
        rows:
            New terminal height.
        """
        if self._pty is None or self._closed:
            return

        self._cols = cols
        self._rows = rows
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._pty.set_size, cols, rows)
        except Exception:
            logger.debug("ConPTY resize error", exc_info=True)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def is_alive(self) -> bool:
        """Whether the child process is still running."""
        if self._pty is None or self._closed:
            return False
        try:
            return self._pty.isalive()
        except Exception:
            return False

    @property
    def exit_code(self) -> Optional[int]:
        """Exit code of the child process, or ``None`` if still running."""
        if self._pty is None or self._closed:
            return None
        try:
            return self._pty.get_exitstatus()
        except Exception:
            return None

    @property
    def pid(self) -> Optional[int]:
        """PID of the child process, or ``None``."""
        if self._pty is None or self._closed:
            return None
        try:
            return self._pty.pid
        except Exception:
            return None
