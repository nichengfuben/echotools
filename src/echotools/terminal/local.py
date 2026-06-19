from __future__ import annotations

"""Local terminal session -- Windows (asyncio subprocess) and Unix (pty)."""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from typing import Optional

from .session import TerminalCallback, TerminalSession

logger = logging.getLogger(__name__)


class LocalTerminal(TerminalSession):
    """Terminal session backed by a local shell process.

    On **Windows** the implementation uses ``asyncio.create_subprocess_exec``
    to spawn ``cmd.exe`` with UTF-8 codepage and ANSI colour support.  Only
    pipe-based I/O is available, so terminal resize is a no-op.

    On **Unix** a pseudo-terminal is allocated via ``pty.openpty()`` and a
    shell process is started with ``subprocess.Popen``.  Window-size changes
    are propagated through ``ioctl(TIOCSWINSZ)``.
    """

    def __init__(
        self,
        session_id: str,
        callback: Optional[TerminalCallback] = None,
    ) -> None:
        super().__init__(session_id=session_id, kind="local", callback=callback)

        # Windows-specific handles
        self._async_process: Optional[asyncio.subprocess.Process] = None

        # Unix-specific handles
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._fd: Optional[int] = None  # pty master fd

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

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
        try:
            encoded = data.encode("utf-8")
            if self._async_process is not None and self._async_process.stdin is not None:
                self._async_process.stdin.write(encoded)
                await self._async_process.stdin.drain()
            elif self._fd is not None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, os.write, self._fd, encoded)
            elif self._process is not None and self._process.stdin is not None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._write_stdin_sync, encoded)
        except Exception:
            logger.debug("write failed (session %s)", self.session_id, exc_info=True)

    async def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal (Unix only; no-op on Windows)."""
        self.cols = cols
        self.rows = rows
        if self._fd is not None:
            self._set_pty_size(cols, rows)

    async def close(self) -> None:
        """Terminate the session and clean up resources."""
        self.alive = False

        # 1. Cancel reader task
        await self._cancel_reader()

        # 2. Close pty fd
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None

        # 3. Terminate async process (Windows)
        if self._async_process is not None:
            try:
                self._async_process.terminate()
                await asyncio.wait_for(self._async_process.wait(), timeout=3)
            except Exception:
                try:
                    self._async_process.kill()
                except Exception:
                    pass

        # 4. Terminate sync process (Unix)
        if self._process is not None:
            try:
                if sys.platform != "win32":
                    try:
                        os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                    except Exception:
                        pass
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Windows implementation
    # ------------------------------------------------------------------

    async def _start_windows(self, cols: int, rows: int) -> bool:
        """Start local terminal on Windows using asyncio subprocess."""
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PYTHONIOENCODING"] = "utf-8"
        env["ANSICON"] = "1"

        try:
            self._async_process = await asyncio.create_subprocess_exec(
                "cmd.exe",
                "/K",
                "chcp 65001 >nul & prompt $P$G",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
        except Exception as exc:
            await self._fire_error(f"Failed to start Windows terminal: {exc}")
            return False

        self.alive = True
        self._reader_task = asyncio.ensure_future(self._read_windows())
        return True

    async def _read_windows(self) -> None:
        """Read from Windows process stdout and fire output callbacks."""
        proc = self._async_process
        if proc is None or proc.stdout is None:
            return
        try:
            while self.alive and proc.returncode is None:
                try:
                    data = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if not data:
                    break
                await self._fire_output(data.decode("utf-8", errors="replace"))
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Windows reader error", exc_info=True)
        finally:
            code = proc.returncode if proc else -1
            await self._fire_exit(code if code is not None else -1)

    # ------------------------------------------------------------------
    # Unix implementation
    # ------------------------------------------------------------------

    async def _start_unix(self, cols: int, rows: int) -> bool:
        """Start local terminal on Unix using pty."""
        import pty

        master_fd, slave_fd = pty.openpty()
        shell = os.environ.get("SHELL", "/bin/bash")

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLUMNS"] = str(cols)
        env["LINES"] = str(rows)

        self._process = subprocess.Popen(
            [shell],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=os.setsid,
            bufsize=0,
        )
        os.close(slave_fd)
        self._fd = master_fd
        self.alive = True

        # Set initial window size
        self._set_pty_size(cols, rows)

        # Start reader
        loop = asyncio.get_event_loop()
        self._reader_task = loop.create_task(self._read_pty())
        return True

    async def _read_pty(self) -> None:
        """Read from pty master fd and fire output callbacks."""
        loop = asyncio.get_event_loop()
        try:
            while self.alive and self._fd is not None:
                data = await loop.run_in_executor(None, self._read_pty_chunk)
                if data is None:
                    break
                if data:
                    await self._fire_output(data.decode("utf-8", errors="replace"))
        except Exception:
            logger.debug("PTY reader error", exc_info=True)
        finally:
            code = self._process.returncode if self._process else -1
            await self._fire_exit(code if code is not None else -1)

    def _read_pty_chunk(self) -> Optional[bytes]:
        """Read a chunk from the pty fd (blocking, runs in executor)."""
        if self._fd is None:
            return None
        try:
            data = os.read(self._fd, 4096)
            if not data:
                return None
            return data
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _set_pty_size(self, cols: int, rows: int) -> None:
        """Set pty window size via ioctl (Unix only, no-op on Windows)."""
        if self._fd is None or sys.platform == "win32":
            return
        try:
            import fcntl
            import struct
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            logger.debug("Failed to set pty size", exc_info=True)

    def _write_stdin_sync(self, data: bytes) -> None:
        """Write data to process stdin and flush (sync helper)."""
        if self._process is not None and self._process.stdin is not None:
            self._process.stdin.write(data)
            self._process.stdin.flush()
