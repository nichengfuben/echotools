from __future__ import annotations

"""通用列表缓存：持久化 + 定时刷新 + 合并策略。

从 ModelsCache 抽象为完全通用的版本，不预设"模型"语义。
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from echotools.base.logger.manager import get_logger

__all__ = ["ListCache"]

logger = get_logger(__name__)


class ListCache:
    """持久化字符串列表；定时 fetch 刷新，overwrite 控制覆盖或只增不减。"""

    def __init__(
        self,
        name: str,
        fallback: List[str],
        cache_path: str,
        overwrite: bool = True,
        data_key: str = "items",
    ) -> None:
        self._name = name
        self._fallback = list(fallback)
        self._overwrite = overwrite
        self._items: List[str] = list(fallback)
        self._cache_path = Path(cache_path)
        self._refreshing = False
        self._data_key = data_key

    async def load(self) -> List[str]:
        try:
            if self._cache_path.is_file():
                text = self._cache_path.read_text(encoding="utf-8")
                data = json.loads(text)
                items = data.get(self._data_key, [])
                if items:
                    self._items = list(items)
                    logger.debug(
                        "[%s] 从缓存加载 %d 项",
                        self._name,
                        len(self._items),
                    )
        except Exception as e:
            logger.warning("[%s] 缓存加载失败: %s", self._name, e)
        return list(self._items)

    async def save(self, items: List[str]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {self._data_key: items, "updated_at": int(time.time())}
            self._cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[%s] 缓存保存失败: %s", self._name, e)

    def _merge(self, remote: List[str]) -> List[str]:
        if self._overwrite:
            return list(remote) if remote else list(self._items)
        existing = set(self._items)
        merged = list(self._items)
        for m in remote:
            if m not in existing:
                merged.append(m)
                existing.add(m)
        return merged

    async def start_refresh_loop(
        self,
        fetch_fn: Callable[[], Awaitable[List[str]]],
        interval: int = 86400,
        on_update: Optional[
            Callable[[List[str]], Awaitable[None]]
        ] = None,
    ) -> None:
        while True:
            await self._do_refresh(fetch_fn, on_update)
            await asyncio.sleep(interval)

    async def _do_refresh(
        self,
        fetch_fn: Callable[[], Awaitable[List[str]]],
        on_update: Optional[
            Callable[[List[str]], Awaitable[None]]
        ] = None,
    ) -> None:
        """执行一次刷新。"""
        if self._refreshing:
            return
        self._refreshing = True
        try:
            remote = await fetch_fn()
            if remote:
                merged = self._merge(remote)
                self._items = merged
                await self.save(merged)
                if on_update is not None:
                    await on_update(merged)
                logger.debug(
                    "[%s] 列表已刷新: %d 项", self._name, len(merged)
                )
        except Exception as e:
            logger.warning("[%s] 列表刷新失败: %s", self._name, e)
        finally:
            self._refreshing = False

    @property
    def items(self) -> List[str]:
        """当前列表副本。"""
        return list(self._items)
