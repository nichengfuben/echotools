"""请求日志存储 + WebSocket 广播。"""

import asyncio
import json
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Set

import aiohttp.web

__all__ = ["RequestBroker", "request_broker"]

MAX_BUFFER = 100


class RequestBroker:
    """请求事件广播器 + 环形缓冲。"""

    def __init__(self) -> None:
        self._sockets: Set[aiohttp.web.WebSocketResponse] = set()
        self._lock = asyncio.Lock()
        self._buffer: Deque[Dict[str, Any]] = deque(maxlen=MAX_BUFFER)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Track in-progress requests: id -> accumulated data
        self._active: Dict[str, Dict[str, Any]] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def has_listeners(self) -> bool:
        return bool(self._sockets)

    async def register(self, ws: aiohttp.web.WebSocketResponse) -> None:
        async with self._lock:
            self._sockets.add(ws)

    async def unregister(self, ws: aiohttp.web.WebSocketResponse) -> None:
        async with self._lock:
            self._sockets.discard(ws)

    async def send_history(self, ws: aiohttp.web.WebSocketResponse) -> int:
        async with self._lock:
            history = list(self._buffer)
            count = 0
            for entry in history:
                try:
                    await ws.send_json(entry)
                    count += 1
                except Exception:
                    break
            # Also send active requests
            for req_id, data in self._active.items():
                try:
                    await ws.send_json({"type": "request_start", **data})
                    count += 1
                except Exception:
                    break
            return count

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        # Store completed requests in buffer
        if payload.get("type") == "request_end":
            self._buffer.append(payload)
            req_id = payload.get("id", "")
            self._active.pop(req_id, None)
        elif payload.get("type") == "request_start":
            req_id = payload.get("id", "")
            self._active[req_id] = {k: v for k, v in payload.items() if k != "type"}

        if not self._sockets:
            return

        message = json.dumps(payload, ensure_ascii=False)
        stale: Set[aiohttp.web.WebSocketResponse] = set()
        async with self._lock:
            for ws in self._sockets:
                try:
                    await ws.send_str(message)
                except Exception:
                    stale.add(ws)
            for ws in stale:
                self._sockets.discard(ws)

    def push_event(self, payload: Dict[str, Any]) -> None:
        """Thread-safe push from middleware (sync context)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)

    def get_recent(self, limit: int = 50) -> list:
        """Return recent completed requests."""
        items = list(self._buffer)
        return items[-limit:]


request_broker = RequestBroker()
