from __future__ import annotations

"""Abstract base class for terminal sessions and callback protocol."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


@dataclass
class TerminalCallback:
    """Callback handlers for terminal session events.

    All callbacks are optional.  When set, they are invoked by the session
    to report output, errors, and exit events.

    Attributes:
        on_output: Called when the terminal produces output data.
        on_error:  Called when the terminal encounters an error.
        on_exit:   Called when the terminal session exits.
    """

    on_output: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    on_error: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    on_exit: Optional[Callable[[int], Coroutine[Any, Any, None]]] = None


class TerminalSession(ABC):
    """Abstract base class for terminal sessions.

    Subclasses implement platform-specific or transport-specific terminal
    logic (local shell, SSH, etc.) while sharing a common async interface.

    Attributes:
        session_id: Unique identifier for this session.
        kind:       Session type string (e.g. ``"local"``, ``"ssh"``).
        alive:      Whether the session is currently running.
        cols:       Current terminal width in columns.
        rows:       Current terminal height in rows.
    """

    def __init__(
        self,
        session_id: str,
        kind: str = "local",
        callback: Optional[TerminalCallback] = None,
    ) -> None:
        self.session_id: str = session_id
        self.kind: str = kind
        self.alive: bool = False
        self.cols: int = 80
        self.rows: int = 24
        self._callback: Optional[TerminalCallback] = callback
        self._reader_task: Optional[asyncio.Task[None]] = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self, cols: int = 80, rows: int = 24) -> bool:
        """Start the terminal session.

        Args:
            cols: Initial terminal width.
            rows: Initial terminal height.

        Returns:
            ``True`` if the session started successfully, ``False`` otherwise.
        """
        ...

    @abstractmethod
    async def write(self, data: str) -> None:
        """Write input data to the terminal.

        Args:
            data: UTF-8 string to send to the terminal process.
        """
        ...

    @abstractmethod
    async def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal.

        Args:
            cols: New terminal width.
            rows: New terminal height.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Terminate the session and release all resources."""
        ...

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    async def _fire_output(self, data: str) -> None:
        """Invoke the *on_output* callback if set."""
        cb = self._callback
        if cb and cb.on_output is not None:
            try:
                await cb.on_output(data)
            except Exception:
                logger.exception("on_output callback raised")

    async def _fire_error(self, message: str) -> None:
        """Invoke the *on_error* callback if set."""
        cb = self._callback
        if cb and cb.on_error is not None:
            try:
                await cb.on_error(message)
            except Exception:
                logger.exception("on_error callback raised")

    async def _fire_exit(self, code: int) -> None:
        """Invoke the *on_exit* callback if set."""
        cb = self._callback
        if cb and cb.on_exit is not None:
            try:
                await cb.on_exit(code)
            except Exception:
                logger.exception("on_exit callback raised")

    async def _cancel_reader(self) -> None:
        """Cancel the reader task if it is still running."""
        task = self._reader_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._reader_task = None
