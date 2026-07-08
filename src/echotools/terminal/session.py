from __future__ import annotations

"""Abstract base class for terminal sessions and callback protocol.

Supports multi-client attachment, offline output buffering, history
management, subprocess monitoring, and process keep-alive across
client disconnections.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum offline buffer size (5 MB).
MAX_OFFLINE_BUFFER_BYTES: int = 5 * 1024 * 1024

# Maximum history lines (5000 lines, same as T3 Code).
MAX_HISTORY_LINES: int = 5000


@dataclass
class TerminalCallback:
    """Callback handlers for terminal session events.

    All callbacks are optional.  When set, they are invoked by the session
    to report output, errors, exit events, and metadata changes.

    Attributes:
        on_output:  Called when the terminal produces output data.
        on_error:   Called when the terminal encounters an error.
        on_exit:    Called when the terminal session exits.
        on_metadata: Called when subprocess state changes.
    """

    on_output: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    on_error: Optional[Callable[[str], Coroutine[Any, Any, None]]] = None
    on_exit: Optional[Callable[[int], Coroutine[Any, Any, None]]] = None
    on_metadata: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None


class TerminalSession(ABC):
    """Abstract base class for terminal sessions.

    Subclasses implement platform-specific or transport-specific terminal
    logic (local shell, SSH, etc.) while sharing a common async interface.

    Multi-client support
    --------------------
    A session can have zero or more attached callbacks.  When at least
    one callback is attached, output is delivered to all of them.
    When no callbacks are attached (after ``detach()``), output is
    buffered in an offline buffer (bounded by ``MAX_OFFLINE_BUFFER_BYTES``).

    Attributes:
        session_id: Unique identifier for this session.
        kind:       Session type string (e.g. ``"local"``, ``"ssh"``).
        alive:      Whether the session process is still running.
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

        # Multi-client callback list.  If a single callback is provided
        # in the constructor, it is added to this list for backward
        # compatibility.
        self._callbacks: List[TerminalCallback] = []
        if callback is not None:
            self._callbacks.append(callback)

        # Legacy single-callback reference (kept for backward compat).
        self._callback: Optional[TerminalCallback] = callback

        self._reader_task: Optional[asyncio.Task[None]] = None

        # Detach / offline buffering state
        self._detached: bool = False
        self._offline_buffer: str = ""
        self._offline_buffer_size: int = 0

        # History management (same as T3 Code)
        self._history: str = ""
        self._history_lines: int = 0
        self._pending_control_sequence: str = ""

        # Subprocess monitoring
        self._has_running_subprocess: bool = False
        self._child_command_label: Optional[str] = None
        self._subprocess_monitor_task: Optional[asyncio.Task[None]] = None

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
    # New operations (same as T3 Code)
    # ------------------------------------------------------------------

    async def clear_history(self) -> None:
        """Clear terminal history.

        This clears the accumulated visible text and the offline buffer.
        Subclasses may override to also clear persisted history files.
        """
        self._history = ""
        self._history_lines = 0
        self._offline_buffer = ""
        self._offline_buffer_size = 0
        logger.debug("Session %s history cleared", self.session_id)

    async def restart(self, cols: int = 80, rows: int = 24) -> bool:
        """Restart the terminal session.

        Kills the current process and starts a new one. The session ID
        is preserved. Returns True if restart was successful.

        Subclasses should override this to implement the actual restart logic.
        """
        await self.close()
        return await self.start(cols=cols, rows=rows)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    @property
    def history(self) -> str:
        """The accumulated visible text history."""
        return self._history

    @property
    def history_lines(self) -> int:
        """Number of lines in history."""
        return self._history_lines

    def _append_history(self, text: str) -> None:
        """Append text to history, capping at MAX_HISTORY_LINES.

        This method strips ephemeral control sequences before appending.
        """
        from .sanitize import sanitize_terminal_history_chunk

        # Sanitize the output
        cleaned, self._pending_control_sequence = sanitize_terminal_history_chunk(
            text, self._pending_control_sequence
        )

        if not cleaned:
            return

        # Append to history
        self._history += cleaned

        # Count lines and cap if necessary
        lines = self._history.split("\n")
        if len(lines) > MAX_HISTORY_LINES:
            # Keep the last MAX_HISTORY_LINES lines
            self._history = "\n".join(lines[-MAX_HISTORY_LINES:])
            self._history_lines = MAX_HISTORY_LINES
        else:
            self._history_lines = len(lines)

    # ------------------------------------------------------------------
    # Subprocess monitoring
    # ------------------------------------------------------------------

    @property
    def has_running_subprocess(self) -> bool:
        """Whether there are running child processes."""
        return self._has_running_subprocess

    @property
    def child_command_label(self) -> Optional[str]:
        """The command name of the most recent child process."""
        return self._child_command_label

    async def _start_subprocess_monitor(self) -> None:
        """Start background task to monitor child processes."""
        if self._subprocess_monitor_task is not None:
            return
        self._subprocess_monitor_task = asyncio.ensure_future(
            self._monitor_subprocesses()
        )

    async def _stop_subprocess_monitor(self) -> None:
        """Stop the subprocess monitoring task."""
        task = self._subprocess_monitor_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._subprocess_monitor_task = None

    async def _monitor_subprocesses(self) -> None:
        """Background task to poll for child processes."""
        try:
            while self.alive:
                await asyncio.sleep(1.0)  # Poll every 1 second
                try:
                    children = await self.get_child_processes()
                    has_running = len(children) > 0
                    command_label = children[0]["command_name"] if children else None

                    # Only notify if state changed
                    if (has_running != self._has_running_subprocess or
                            command_label != self._child_command_label):
                        self._has_running_subprocess = has_running
                        self._child_command_label = command_label
                        await self._fire_metadata({
                            "has_running_subprocess": has_running,
                            "child_command_label": command_label,
                        })
                except Exception:
                    pass  # Ignore monitoring errors
        except asyncio.CancelledError:
            pass

    async def get_child_processes(self) -> List[Dict[str, Any]]:
        """Get child processes running under this terminal's PID.

        Returns a list of dicts with keys: pid, command_name.
        Subclasses should override this for platform-specific implementation.
        """
        return []

    async def _fire_metadata(self, metadata: Dict[str, Any]) -> None:
        """Invoke the on_metadata callback on all attached clients."""
        for cb in list(self._callbacks):
            if cb.on_metadata is not None:
                try:
                    await cb.on_metadata(metadata)
                except Exception:
                    logger.exception("on_metadata callback raised")

    # ------------------------------------------------------------------
    # Detach / attach / kill  (process keep-alive)
    # ------------------------------------------------------------------

    def detach(self) -> None:
        """Detach all clients.  The shell process keeps running; output
        is buffered to the offline buffer until a client reattaches.
        """
        self._detached = True
        self._callbacks.clear()
        self._callback = None
        logger.debug("Session %s detached (process kept alive)", self.session_id)

    def attach(self, callback: TerminalCallback) -> str:
        """Attach a new client callback.

        Returns the buffered offline output (which the caller should
        deliver to the newly attached client).  The offline buffer is
        cleared after retrieval.
        """
        self._detached = False
        self._callbacks.append(callback)
        # Keep _callback in sync for backward compat
        if self._callback is None:
            self._callback = callback

        # Retrieve and clear offline buffer
        buffered = self._offline_buffer
        self._offline_buffer = ""
        self._offline_buffer_size = 0

        logger.debug(
            "Session %s attached (buffered %d bytes)", self.session_id, len(buffered)
        )
        return buffered

    def detach_callback(self, callback: TerminalCallback) -> None:
        """Remove a specific callback (e.g. one client disconnects
        while others remain).

        If no callbacks remain after removal, the session auto-detaches
        (process keeps running, output buffered).
        """
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass
        if not self._callbacks:
            self._detached = True
            self._callback = None
        else:
            # Update legacy reference
            self._callback = self._callbacks[0] if self._callbacks else None

    @property
    def attached_count(self) -> int:
        """Number of currently attached client callbacks."""
        return len(self._callbacks)

    @property
    def is_detached(self) -> bool:
        """Whether the session has no attached clients."""
        return self._detached or len(self._callbacks) == 0

    @property
    def offline_output(self) -> str:
        """The current offline output buffer contents."""
        return self._offline_buffer

    @property
    def pid(self) -> Optional[int]:
        """PID of the underlying process, if available.

        Subclasses should override this to return the actual PID.
        """
        return None

    @property
    def is_alive(self) -> bool:
        """Whether the underlying process is still running."""
        return self.alive

    # ------------------------------------------------------------------
    # Helpers available to subclasses
    # ------------------------------------------------------------------

    async def _fire_output(self, data: str) -> None:
        """Invoke the *on_output* callback on all attached clients.

        When no clients are attached, buffer the output for later
        delivery. Also appends to history for persistence.
        """
        # Always append to history (even when detached)
        self._append_history(data)

        if not self._callbacks:
            # Buffer offline output
            self._offline_buffer += data
            self._offline_buffer_size += len(data)
            # Trim if over limit (keep the tail)
            if self._offline_buffer_size > MAX_OFFLINE_BUFFER_BYTES:
                excess = self._offline_buffer_size - MAX_OFFLINE_BUFFER_BYTES
                self._offline_buffer = self._offline_buffer[excess:]
                self._offline_buffer_size = len(self._offline_buffer)
            return

        for cb in list(self._callbacks):
            if cb.on_output is not None:
                try:
                    await cb.on_output(data)
                except Exception:
                    logger.exception("on_output callback raised")

    async def _fire_error(self, message: str) -> None:
        """Invoke the *on_error* callback on all attached clients."""
        for cb in list(self._callbacks):
            if cb.on_error is not None:
                try:
                    await cb.on_error(message)
                except Exception:
                    logger.exception("on_error callback raised")

    async def _fire_exit(self, code: int) -> None:
        """Invoke the *on_exit* callback on all attached clients."""
        self.alive = False
        for cb in list(self._callbacks):
            if cb.on_exit is not None:
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
