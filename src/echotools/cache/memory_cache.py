from __future__ import annotations

"""带 TTL 的内存缓存。"""

import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple

__all__ = ["MemoryCache"]


class MemoryCache:
    """Thread-safe TTL memory cache with optional LRU eviction."""

    def __init__(self, default_ttl: float = 0.0, max_size: int = 0) -> None:
        """初始化缓存。

        Args:
            default_ttl: 默认存活秒数，0 表示永不过期。
            max_size: 最大条目数，0 表示不限制。
        """
        self._store: "OrderedDict[str, Tuple[Any, float]]" = OrderedDict()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._lock = threading.RLock()

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """写入缓存。"""
        effective = self._default_ttl if ttl is None else ttl
        expire = 0.0 if effective <= 0 else time.time() + effective
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expire)
            self._evict_if_needed()

    def get(self, key: str, default: Any = None) -> Any:
        """读取缓存。"""
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return default
            value, expire = item
            if expire and time.time() > expire:
                self._store.pop(key, None)
                return default
            self._store.move_to_end(key)
            return value

    def delete(self, key: str) -> None:
        """删除键。"""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """清空缓存。"""
        with self._lock:
            self._store.clear()

    def cleanup(self) -> int:
        """清理过期项，返回清理数量。"""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if exp and now > exp]
            for k in expired:
                self._store.pop(k, None)
            return len(expired)

    def _evict_if_needed(self) -> None:
        if self._max_size <= 0:
            return
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)
