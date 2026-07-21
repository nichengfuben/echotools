from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..session import TerminalCallback

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

class LocalTerminalWindowsMixin:

    async def _start_windows(self, cols: int, rows: int) -> bool:
        """Start local terminal on Windows.

        Uses shell fallback chain (same as T3 Code):
        pwsh.exe → PowerShell path → powershell.exe → ComSpec → cmd.exe

        Prefers ConPTY (via *pywinpty*) when available.  Falls back to
        ``asyncio.create_subprocess_exec`` with plain pipes otherwise.
        """
        # Resolve shell candidates
        shell_candidates = self._resolve_windows_shell_candidates()

        for shell_info in shell_candidates:
            shell, args, cmdline = shell_info

            if _HAS_CONPTY:
                try:
                    ok = await self._start_conpty(cols, rows, shell, cmdline)
                    if ok:
                        return True
                except Exception as exc:
                    logger.warning(
                        "ConPTY start failed for %s, trying next: %s", shell, exc
                    )
            else:
                try:
                    ok = await self._start_windows_pipe(cols, rows, shell, args, cmdline)
                    if ok:
                        return True
                except Exception as exc:
                    logger.warning(
                        "Pipe start failed for %s, trying next: %s", shell, exc
                    )

        await self._fire_error("Failed to start Windows terminal: no usable shell found")
        return False

    async def _start_conpty(self, cols: int, rows: int, shell: str = "cmd.exe", cmdline: str = None) -> bool:
        """Start local terminal on Windows using ConPTY."""
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["PYTHONIOENCODING"] = "utf-8"
        env["ANSICON"] = "1"

        handle = ConPTYHandle(cols=cols, rows=rows)
        if cmdline is None and ("cmd" in shell.lower()):
            cmdline = "/K chcp 65001 >nul & prompt $P$G"
        ok = handle.spawn(
            shell,
            cmdline=cmdline,
            env=env,
        )
        if not ok:
            await handle.close()
            raise RuntimeError("ConPTY spawn returned False")

        self._conpty = handle
        self._pid = handle.pid
        self.alive = True
        self._reader_task = asyncio.ensure_future(self._read_conpty())
        await self._start_subprocess_monitor()
        logger.debug("ConPTY terminal started (pid=%s, shell=%s)", handle.pid, shell)
        return True

    async def _read_conpty(self) -> None:
        """Read from ConPTY and fire output callbacks."""
        handle = self._conpty
        if handle is None:
            return
        try:
            while self.alive and handle.is_alive:
                await self._wait_if_output_paused()
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

    async def _start_windows_pipe(self, cols: int, rows: int, shell: str = "cmd.exe", args: List[str] = None, cmdline: str = None) -> bool:
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
            # Build command arguments
            cmd_args = [shell]
            if args:
                cmd_args.extend(args)
            if cmdline:
                cmd_args.extend(cmdline.split())

            self._async_process = await asyncio.create_subprocess_exec(
                *cmd_args,
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
        await self._start_subprocess_monitor()
        return True

    async def _read_windows(self) -> None:
        """Read from Windows process stdout and fire output callbacks."""
        proc = self._async_process
        if proc is None or proc.stdout is None:
            return
        try:
            while self.alive and proc.returncode is None:
                await self._wait_if_output_paused()
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

