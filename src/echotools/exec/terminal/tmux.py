from __future__ import annotations

"""tmux-backed terminal session — survives provider process restart on Unix."""

import asyncio
import logging
import shutil
import sys
from typing import Optional

from .local import LocalTerminal

logger = logging.getLogger(__name__)

__all__ = ["TmuxTerminal", "tmux_available"]


def tmux_available() -> bool:
    """Return True when ``tmux`` is on PATH (non-Windows only)."""
    if sys.platform == "win32":
        return False
    return shutil.which("tmux") is not None


class TmuxTerminal(LocalTerminal):
    """Local terminal inside a detached tmux session.

    On start, creates ``tmux new-session -d -s <name>`` when missing, then
    attaches via ``tmux attach -t <name>`` in a PTY so the WebSocket client
    gets a live interactive shell.  The tmux server outlives the provider
    process, enabling restart recovery when ``backend=tmux``.
    """

    def __init__(
        self,
        session_id: str,
        tmux_session_name: Optional[str] = None,
        **kwargs: object,
    ) -> None:
        super().__init__(session_id, **kwargs)  # type: ignore[arg-type]
        self.kind = "tmux"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
        self._tmux_name = tmux_session_name or f"pv2_{safe[:48]}"

    async def start(self, cols: int = 80, rows: int = 24) -> bool:
        if sys.platform == "win32":
            await self._fire_error("tmux backend is not supported on Windows")
            return False
        if not tmux_available():
            await self._fire_error("tmux is not installed or not on PATH")
            return False
        self.cols = cols
        self.rows = rows
        try:
            if not await self._tmux_session_exists():
                ok = await self._tmux_create_detached(cols, rows)
                if not ok:
                    return False
            return await self._start_tmux_attach(cols, rows)
        except Exception as exc:
            await self._fire_error(f"Failed to start tmux terminal: {exc}")
            return False

    async def _tmux_session_exists(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            self._tmux_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0

    async def _tmux_create_detached(self, cols: int, rows: int) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            "new-session",
            "-d",
            "-s",
            self._tmux_name,
            "-x",
            str(cols),
            "-y",
            str(rows),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            await self._fire_error(
                detail or f"tmux new-session failed (code {proc.returncode})"
            )
            return False
        return True

    async def _start_tmux_attach(self, cols: int, rows: int) -> bool:
        """Spawn ``tmux attach`` in a Unix PTY (reuse LocalTerminal unix path)."""
        return await self._start_unix_pty_command(
            ["tmux", "attach", "-t", self._tmux_name],
            cols,
            rows,
        )
