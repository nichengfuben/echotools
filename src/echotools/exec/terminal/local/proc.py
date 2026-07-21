from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..session import TerminalCallback

if TYPE_CHECKING:
    from .core import LocalTerminal

logger = logging.getLogger(__name__)

try:
    from ..conpty import ConPTYHandle
    _HAS_CONPTY = True
except ImportError:
    ConPTYHandle = None  # type: ignore[assignment, misc]
    _HAS_CONPTY = False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False

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

class LocalTerminalProcMixin:

    async def get_child_processes(self) -> List[Dict[str, Any]]:
        """Get child processes running under this terminal's PID.

        Uses platform-specific commands:
        - Windows: Get-CimInstance Win32_Process via PowerShell
        - POSIX: pgrep -P <pid> → ps -eo pid=,ppid=,comm=

        Returns a list of dicts with keys: pid, command_name.
        """
        if self._pid is None or not self.is_alive:
            return []

        try:
            if sys.platform == "win32":
                return await self._get_child_processes_windows()
            else:
                return await self._get_child_processes_posix()
        except Exception:
            return []

    async def _get_child_processes_windows(self) -> List[Dict[str, Any]]:
        """Get child processes on Windows using PowerShell."""
        cmd = (
            f"Get-CimInstance Win32_Process | "
            f"Where-Object {{$_.ParentProcessId -eq {self._pid}}} | "
            f"Select-Object ProcessId, Name | "
            f"ConvertTo-Json"
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if not stdout:
            return []

        import json
        try:
            data = json.loads(stdout.decode("utf-8", errors="replace"))
            if isinstance(data, list):
                return [{"pid": d["ProcessId"], "command_name": d["Name"]} for d in data]
            elif isinstance(data, dict):
                return [{"pid": data["ProcessId"], "command_name": data["Name"]}]
        except Exception:
            pass
        return []

    async def _get_child_processes_posix(self) -> List[Dict[str, Any]]:
        """Get child processes on POSIX using pgrep and ps."""
        # First get child PIDs
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-P", str(self._pid),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if not stdout:
            return []

        child_pids = stdout.decode().strip().split("\n")
        if not child_pids or child_pids == [""]:
            return []

        # Get command names for child PIDs
        results = []
        for pid in child_pids:
            pid = pid.strip()
            if not pid:
                continue
            ps_proc = await asyncio.create_subprocess_exec(
                "ps", "-o", "comm=", "-p", pid,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            ps_stdout, _ = await ps_proc.communicate()
            if ps_stdout:
                cmd_name = ps_stdout.decode().strip()
                if cmd_name:
                    results.append({"pid": int(pid), "command_name": cmd_name})

        return results


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


    def _resolve_windows_shell_candidates(self) -> List[tuple]:
        """Resolve Windows shell candidates with their arguments.

        Returns a list of (shell, args, cmdline) tuples.
        """
        candidates = []
        for shell in _WINDOWS_SHELL_CANDIDATES:
            if shell is None:
                # Use ComSpec from environment
                shell = os.environ.get("ComSpec", "cmd.exe")
                cmdline = "/K chcp 65001 >nul & prompt $P$G"
                candidates.append((shell, [], cmdline))
            elif shell == "cmd.exe":
                cmdline = "/K chcp 65001 >nul & prompt $P$G"
                candidates.append((shell, [], cmdline))
            elif "powershell" in shell.lower() or "pwsh" in shell.lower():
                args = ["-NoLogo"]
                cmdline = None
                candidates.append((shell, args, cmdline))
            else:
                candidates.append((shell, [], None))
        return candidates

    def _resolve_posix_shell_candidates(self) -> List[str]:
        """Resolve POSIX shell candidates.

        Returns a list of shell paths.
        """
        candidates = []
        for shell in _POSIX_SHELL_CANDIDATES:
            if shell is None:
                # Use $SHELL from environment
                shell = os.environ.get("SHELL", "/bin/sh")
                candidates.append(shell)
            elif not shell.startswith("/"):
                # PATH lookup candidate
                import shutil
                found = shutil.which(shell)
                if found:
                    candidates.append(found)
            else:
                candidates.append(shell)
        return candidates

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if an error is retryable (shell not found, permission denied, etc.)."""
        if isinstance(exc, FileNotFoundError):
            return True
        if isinstance(exc, PermissionError):
            return True
        if isinstance(exc, OSError):
            error_str = str(exc).lower()
            if "not found" in error_str or "no such file" in error_str:
                return True
            if "permission denied" in error_str:
                return True
        return False

    # Session persistence

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
        recovered: Dict[str, "LocalTerminal"] = {}
        if not persist_dir.exists():
            return recovered

        for meta_path in persist_dir.glob("*.json"):
            data = _load_session_meta(meta_path)
            if not data:
                continue
            terminal = _recover_one_session(cls, data, callback_factory)
            if terminal is None:
                continue
            recovered[terminal.session_id] = terminal
            try:
                meta_path.unlink()
            except Exception:
                pass

        return recovered


def _load_session_meta(meta_path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _recover_one_session(
    cls: type,
    data: Dict[str, Any],
    callback_factory: Callable[[str], TerminalCallback],
) -> Optional["LocalTerminal"]:
    session_id = data.get("session_id")
    if not session_id:
        return None

    pid = data.get("pid")
    terminal = cls(session_id=session_id)
    terminal.cols = data.get("cols", 80)
    terminal.rows = data.get("rows", 24)
    terminal._pid = pid

    if pid and _pid_alive(pid):
        terminal.alive = True
        callback = callback_factory(session_id)
        terminal._callbacks.append(callback)
        terminal._callback = callback
        logger.debug("Recovered session %s (pid=%d, alive=True)", session_id, pid)
    else:
        terminal.alive = False
        logger.debug("Recovered session %s (pid=%s, alive=False)", session_id, pid)
    return terminal
