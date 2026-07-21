from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .base import TerminalCallback

logger = logging.getLogger(__name__)

MAX_OFFLINE_BUFFER_BYTES: int = 5 * 1024 * 1024


class SessionClientMixin:
    def detach(self) -> None:
        """Detach all clients.  The shell process keeps running; output
        is buffered to the offline buffer until a client reattaches.
        """
        self._detached = True
        self._callbacks.clear()
        self._callback = None
        logger.debug("Session %s detached (process kept alive)", self.session_id)

    def attach(self, callback: "TerminalCallback") -> str:
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

    def detach_callback(self, callback: "TerminalCallback") -> None:
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
        if data:
            self._record_seq_chunk(data)
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
