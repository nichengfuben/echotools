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

# ConPTY availability (Windows only, requires pywinpty).
try:
    from .conpty import ConPTYHandle

    _HAS_CONPTY = True
except ImportError:
    ConPTYHandle = None  # type: ignore[assignment, misc]
    _HAS_CONPTY = False


class LocalTerminal(TerminalSession):
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
    """

    def __init__(
        self,
        session_id: str,
        callback: Optional[TerminalCallback] = None,
    ) -> None:
        super().__init__(session_id=session_id, kind="local", callback=callback)

        # Windows ConPTY handle (preferred)
        self._conpty: Optional["ConPTYHandle"] = None

        # Windows-specific handles (pipe fallback)
        self._async_process: Optional[asyncio.subprocess.Process] = None
        self._orig_handler = None

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
        except Exception:
            logger.debug("write failed (session %s)", self.session_id, exc_info=True)

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

    async def close(self) -> None:
        """Terminate the session and clean up resources."""
        self.alive = False

        # 1. Cancel reader task
        await self._cancel_reader()

        # 2. Close ConPTY handle (Windows preferred path)
        if self._conpty is not None:
            try:
                await self._conpty.close()
            except Exception:
                pass
            self._conpty = None

        # 3. Close pty fd
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None

        # 4. Terminate async process (Windows pipe fallback)
        if self._async_process is not None:
            proc = self._async_process
            # Close pipes first to prevent proactor ConnectionResetError
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
            self._async_process = None
            # Restore original exception handler
            if self._orig_handler is not None:
                try:
                    asyncio.get_event_loop().set_exception_handler(self._orig_handler)
                except Exception:
                    pass
                self._orig_handler = None

        # 5. Terminate sync process (Unix)
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
        """Start local terminal on Windows.

        Prefers ConPTY (via *pywinpty*) when available.  Falls back to
        ``asyncio.create_subprocess_exec`` with plain pipes otherwise.
        """
        if _HAS_CONPTY:
            try:
                return await self._start_conpty(cols, rows)
            except Exception as exc:
                logger.warning(
                    "ConPTY start failed, falling back to pipe I/O: %s", exc
                )
        return await self._start_windows_pipe(cols, rows)

    async def _start_conpty(self, cols: int, rows: int) -> bool:
        """Start local terminal on Windows using ConPTY."""
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PYTHONIOENCODING"] = "utf-8"
        env["ANSICON"] = "1"

        handle = ConPTYHandle(cols=cols, rows=rows)
        ok = handle.spawn(
            "cmd.exe",
            cmdline="/K chcp 65001 >nul & prompt $P$G",
            env=env,
        )
        if not ok:
            await handle.close()
            raise RuntimeError("ConPTY spawn returned False")

        self._conpty = handle
        self.alive = True
        self._reader_task = asyncio.ensure_future(self._read_conpty())
        logger.info("ConPTY terminal started (pid=%s)", handle.pid)
        return True

    async def _read_conpty(self) -> None:
        """Read from ConPTY and fire output callbacks."""
        handle = self._conpty
        if handle is None:
            return
        try:
            while self.alive and handle.is_alive:
                text = await handle.read()
                if text is None:
                    # Check if still alive -- may have exited cleanly.
                    if not handle.is_alive:
                        break
                    # Transient read failure; retry.
                    await asyncio.sleep(0.05)
                    continue
                if text:
                    await self._fire_output(text)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("ConPTY reader error", exc_info=True)
        finally:
            code = handle.exit_code if handle else -1
            await self._fire_exit(code if code is not None else -1)

    async def _start_windows_pipe(self, cols: int, rows: int) -> bool:
        """Start local terminal on Windows using asyncio subprocess (pipe fallback)."""
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PYTHONIOENCODING"] = "utf-8"
        env["ANSICON"] = "1"

        # Suppress known ConnectionResetError from proactor pipe cleanup.
        # When cmd.exe exits or is killed, the proactor transport tries to
        # shutdown already-closed pipes, raising ConnectionResetError in
        # an event loop callback that our code cannot catch directly.
        loop = asyncio.get_event_loop()
        self._orig_handler = loop.get_exception_handler()

        def _suppress_proactor_error(loop_ref, context):
            exc = context.get("exception")
            if isinstance(exc, ConnectionResetError):
                return  # silently ignore
            if self._orig_handler:
                self._orig_handler(loop_ref, context)
            else:
                loop_ref.default_exception_handler(context)

        loop.set_exception_handler(_suppress_proactor_error)

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
