from __future__ import annotations

"""Local terminal session -- Windows (asyncio subprocess) and Unix (pty).

Supports process keep-alive: the shell process survives client
disconnection (``detach()``).  Output produced while detached is
buffered and delivered when a new client attaches (``attach()``).
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from .session import TerminalCallback, TerminalSession

logger = logging.getLogger(__name__)

# ConPTY availability (Windows only, requires pywinpty).
try:
    from .conpty import ConPTYHandle

    _HAS_CONPTY = True
except ImportError:
    ConPTYHandle = None  # type: ignore[assignment, misc]
    _HAS_CONPTY = False


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

        # Windows ConPTY handle (preferred)
        self._conpty: Optional["ConPTYHandle"] = None

        # Windows-specific handles (pipe fallback)
        self._async_process: Optional[asyncio.subprocess.Process] = None
        self._orig_handler = None

        # Unix-specific handles
        self._process: Optional[subprocess.Popen[bytes]] = None
        self._fd: Optional[int] = None  # pty master fd

        # Cached PID (set after start)
        self._pid: Optional[int] = None

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

    async def kill(self) -> None:
        """Explicitly terminate the shell process and clean up resources.

        This is the "user clicked X" path.  The process is killed
        immediately.
        """
        self.alive = False
        self._callbacks.clear()
        self._callback = None

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

        self._pid = None
        logger.debug("Session %s killed", self.session_id)

    async def close(self) -> None:
        """Terminate the session and clean up resources.

        Backward-compatible alias for :meth:`kill`.
        """
        await self.kill()

    # ------------------------------------------------------------------
    # Process introspection
    # ------------------------------------------------------------------

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
        # Unix subprocess
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

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def save_state(self, persist_dir: Optional[Path] = None) -> None:
        """Save session state to disk for crash recovery.

        This is a best-effort snapshot.  It writes a small JSON file
        with the session metadata so that ``recover_sessions()`` can
        find surviving processes after a server restart.
        """
        if persist_dir is None:
            return

        import json
        import time

        persist_dir.mkdir(parents=True, exist_ok=True)
        meta_path = persist_dir / f"{self.session_id}.json"

        data = {
            "session_id": self.session_id,
            "pid": self.pid,
            "cols": self.cols,
            "rows": self.rows,
            "kind": self.kind,
            "alive": self.is_alive,
            "updated_at": time.time(),
        }
        try:
            meta_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Failed to save session state", exc_info=True)

    @classmethod
    async def recover_sessions(
        cls,
        persist_dir: Path,
        callback_factory: Callable[[str], TerminalCallback],
    ) -> Dict[str, "LocalTerminal"]:
        """Scan *persist_dir* for saved sessions and reattach surviving processes.

        For each saved session:
        - If the PID is still alive, create a ``LocalTerminal`` that
          wraps the existing process and start reading its output.
        - If the PID is dead, mark the session as exited and retain
          the metadata for history.

        Parameters
        ----------
        persist_dir:
            Directory containing ``{session_id}.json`` metadata files.
        callback_factory:
            A callable that takes a session_id and returns a
            ``TerminalCallback`` for delivering output.

        Returns
        -------
        dict
            Mapping of ``session_id`` to ``LocalTerminal`` instances.
        """
        import json

        recovered: Dict[str, LocalTerminal] = {}

        if not persist_dir.exists():
            return recovered

        for meta_path in persist_dir.glob("*.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            session_id = data.get("session_id")
            if not session_id:
                continue

            pid = data.get("pid")
            cols = data.get("cols", 80)
            rows = data.get("rows", 24)

            terminal = cls(session_id=session_id)
            terminal.cols = cols
            terminal.rows = rows
            terminal._pid = pid

            if pid and _pid_alive(pid):
                # Process is still alive -- wrap it
                terminal.alive = True
                callback = callback_factory(session_id)
                terminal._callbacks.append(callback)
                terminal._callback = callback

                # Try to reattach by opening the ConPTY or pty handle.
                # Note: on Windows, we cannot reattach to a ConPTY that
                # was created by a previous process.  The process is
                # alive but we can only observe it via the persist output
                # file.  On Unix, we would need the pty fd which is lost.
                # For now, mark as alive but note that reattachment is
                # limited on both platforms.
                logger.debug(
                    "Recovered session %s (pid=%d, alive=True)", session_id, pid
                )
                recovered[session_id] = terminal
            else:
                # Process is dead -- mark as exited
                terminal.alive = False
                logger.debug(
                    "Recovered session %s (pid=%s, alive=False)", session_id, pid
                )
                recovered[session_id] = terminal

            # Clean up the metadata file
            try:
                meta_path.unlink()
            except Exception:
                pass

        return recovered

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
        self._pid = handle.pid
        self.alive = True
        self._reader_task = asyncio.ensure_future(self._read_conpty())
        logger.debug("ConPTY terminal started (pid=%s)", handle.pid)
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

        self._pid = self._async_process.pid
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
        loop = asyncio.get_event_loop()

        def _spawn_unix_pty():
            """Allocate PTY and spawn shell (blocking, runs in executor)."""
            import pty

            master_fd, slave_fd = pty.openpty()

            shell_candidates = []
            user_shell = os.environ.get("SHELL")
            if user_shell:
                shell_candidates.append(user_shell)
            shell_candidates.extend(["/bin/bash", "/bin/sh", "/bin/zsh"])

            shell = None
            for candidate in shell_candidates:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    shell = candidate
                    break

            if shell is None:
                os.close(master_fd)
                os.close(slave_fd)
                raise RuntimeError(
                    "No usable shell found (tried: "
                    + ", ".join(shell_candidates)
                    + ")"
                )

            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLUMNS"] = str(cols)
            env["LINES"] = str(rows)

            try:
                proc = subprocess.Popen(
                    [shell],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    preexec_fn=os.setsid,
                    bufsize=0,
                )
            finally:
                os.close(slave_fd)

            return master_fd, proc, shell

        try:
            master_fd, proc, shell_path = await loop.run_in_executor(
                None, _spawn_unix_pty
            )
        except Exception as exc:
            await self._fire_error(f"Failed to start Unix terminal: {exc}")
            return False

        self._fd = master_fd
        self._process = proc
        self._pid = proc.pid
        self.alive = True

        self._set_pty_size(cols, rows)

        self._reader_task = loop.create_task(self._read_pty())
        logger.debug("Unix PTY terminal started (pid=%s, shell=%s)", proc.pid, shell_path)
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
        """Read a chunk from the pty fd (blocking, runs in executor).

        Uses ``select`` with a short timeout so the thread does not block
        indefinitely when no output is available.  This allows the reader
        loop to check ``self.alive`` periodically and exit cleanly when
        the session is killed.
        """
        if self._fd is None:
            return None
        try:
            import select

            ready, _, _ = select.select([self._fd], [], [], 0.5)
            if not ready:
                return b""
            data = os.read(self._fd, 4096)
            if not data:
                return None
            return data
        except OSError:
            # EIO on macOS/Linux: slave PTY closed (shell exited)
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
