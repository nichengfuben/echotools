from __future__ import annotations

"""带 TTL 的内存缓存。"""

import time
from typing import Any, Dict, Optional, Tuple

__all__ = ["MemoryCache"]


class MemoryCache:
    """简单的 TTL 内存缓存。"""

    def __init__(self, default_ttl: float = 0.0) -> None:
        """初始化缓存。

        Args:
            default_ttl: 默认存活秒数，0 表示永不过期。
        """
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """写入缓存。

        Args:
            key: 键。
            value: 值。
            ttl: 存活秒数，None 用默认。
        """
        effective = self._default_ttl if ttl is None else ttl
        expire = 0.0 if effective <= 0 else time.time() + effective
        self._store[key] = (value, expire)

    def get(self, key: str, default: Any = None) -> Any:
        """读取缓存。

        Args:
            key: 键。
            default: 缺省值。

        Returns:
            值或默认值（过期自动剔除）。
        """
        item = self._store.get(key)
        if item is None:
            return default
        value, expire = item
        if expire and time.time() > expire:
            self._store.pop(key, None)
            return default
        return value

    def delete(self, key: str) -> None:
        """删除键。"""
        self._store.pop(key, None)

    def clear(self) -> None:
        """清空缓存。"""
        self._store.clear()

    def cleanup(self) -> int:
        """清理过期项，返回清理数量。"""
        now = time.time()
        expired = [
            k
            for k, (_, exp) in self._store.items()
            if exp and now > exp
        ]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)
