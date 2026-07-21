from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

try:
    from ..conpty import ConPTYHandle
    _HAS_CONPTY = True
except ImportError:
    ConPTYHandle = None  # type: ignore[assignment, misc]
    _HAS_CONPTY = False

_WINDOWS_SHELL_CANDIDATES = [
    "pwsh.exe",
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    "powershell.exe",
    None,
    "cmd.exe",
]

_POSIX_SHELL_CANDIDATES = [
    None,
    "/bin/zsh",
    "/bin/bash",
    "/bin/sh",
    "zsh",
    "bash",
    "sh",
]

class LocalTerminalUnixMixin:

    async def _start_unix(self, cols: int, rows: int) -> bool:
        """Start local terminal on Unix using pty."""
        loop = asyncio.get_event_loop()
        shell_candidates = self._resolve_posix_shell_candidates()
        try:
            master_fd, proc, shell_path = await loop.run_in_executor(
                None, spawn_unix_pty, shell_candidates, cols, rows
            )
        except Exception as exc:
            if self._is_retryable_error(exc):
                logger.warning("Shell start failed (retryable): %s", exc)
            await self._fire_error(f"Failed to start Unix terminal: {exc}")
            return False

        self._fd = master_fd
        self._process = proc
        self._pid = proc.pid
        self.alive = True
        self._set_pty_size(cols, rows)
        self._reader_task = loop.create_task(self._read_pty())
        await self._start_subprocess_monitor()
        logger.debug("Unix PTY terminal started (pid=%s, shell=%s)", proc.pid, shell_path)
        return True

    async def _start_unix_pty_command(
        self,
        command: List[str],
        cols: int,
        rows: int,
    ) -> bool:
        """Start an arbitrary command attached to a Unix PTY."""
        loop = asyncio.get_event_loop()

        def _spawn() -> tuple[int, subprocess.Popen[bytes], str]:
            import pty

            master_fd, slave_fd = pty.openpty()
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLUMNS"] = str(cols)
            env["LINES"] = str(rows)
            try:
                proc = subprocess.Popen(
                    command,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    preexec_fn=os.setsid,
                    bufsize=0,
                )
            finally:
                os.close(slave_fd)
            return master_fd, proc, " ".join(command)

        try:
            master_fd, proc, label = await loop.run_in_executor(None, _spawn)
        except Exception as exc:
            await self._fire_error(f"Failed to start PTY command: {exc}")
            return False

        self._fd = master_fd
        self._process = proc
        self._pid = proc.pid
        self.alive = True
        self._set_pty_size(cols, rows)
        self._reader_task = loop.create_task(self._read_pty())
        await self._start_subprocess_monitor()
        logger.debug("Unix PTY command started (pid=%s, cmd=%s)", proc.pid, label)
        return True

    async def _read_pty(self) -> None:
        """Read from pty master fd and fire output callbacks."""
        loop = asyncio.get_event_loop()
        try:
            while self.alive and self._fd is not None:
                await self._wait_if_output_paused()
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


def _resolve_posix_shell(candidates: List[str]) -> str:
    for candidate in candidates:
        if not candidate.startswith("/"):
            import shutil as sh
            found = sh.which(candidate)
            if found:
                candidate = found
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("No usable shell found (tried: " + ", ".join(candidates) + ")")


def _shell_args_for(shell: str) -> List[str]:
    if "zsh" in shell:
        return ["-o", "nopromptsp"]
    if "powershell" in shell.lower() or "pwsh" in shell.lower():
        return ["-NoLogo"]
    return []


def spawn_unix_pty(
    shell_candidates: List[str], cols: int, rows: int
) -> tuple[int, subprocess.Popen[bytes], str]:
    import pty

    master_fd, slave_fd = pty.openpty()
    shell = _resolve_posix_shell(shell_candidates)
    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)
    try:
        proc = subprocess.Popen(
            [shell] + _shell_args_for(shell),
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

