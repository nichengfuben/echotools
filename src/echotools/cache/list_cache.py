from __future__ import annotations

"""通用列表缓存：持久化 + 定时刷新 + 合并策略。

从 ModelsCache 抽象为完全通用的版本，不预设"模型"语义。
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from echotools.logger.manager import get_logger

__all__ = ["ListCache"]

logger = get_logger(__name__)


class ListCache:
    """通用字符串列表缓存管理器。

    职责：
    1. 从持久化文件读取缓存
    2. 定时调用 fetch_fn 刷新远程列表
    3. 根据 overwrite 决定覆盖或追加
    4. 更新后触发 on_update 回调
    """

    def __init__(
        self,
        name: str,
        fallback: List[str],
        cache_path: str,
        overwrite: bool = True,
    ) -> None:
        """初始化列表缓存。

        Args:
            name: 缓存标识名（仅用于日志）。
            fallback: 兜底列表。
            cache_path: 持久化文件路径。
            overwrite: True=覆盖，False=只增不减。
        """
        self._name = name
        self._fallback = list(fallback)
        self._overwrite = overwrite
        self._items: List[str] = list(fallback)
        self._cache_path = Path(cache_path)
        self._refreshing = False

    async def load(self) -> List[str]:
        """从缓存文件加载列表。

        Returns:
            缓存列表，无缓存则返回兜底列表。
        """
        try:
            if self._cache_path.is_file():
                text = self._cache_path.read_text(encoding="utf-8")
                data = json.loads(text)
                items = data.get("items", [])
                if items:
                    self._items = list(items)
                    logger.info(
                        "[%s] 从缓存加载 %d 项",
                        self._name,
                        len(self._items),
                    )
        except Exception as e:
            logger.warning("[%s] 缓存加载失败: %s", self._name, e)
        return list(self._items)

    async def save(self, items: List[str]) -> None:
        """保存列表到缓存文件。

        Args:
            items: 要保存的列表。
        """
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"items": items, "updated_at": int(time.time())}
            self._cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("[%s] 缓存保存失败: %s", self._name, e)

    def _merge(self, remote: List[str]) -> List[str]:
        """根据策略合并列表。"""
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
        """启动定时刷新循环（永久运行）。

        Args:
            fetch_fn: 返回远程列表的异步函数。
            interval: 刷新间隔（秒）。
            on_update: 更新回调。
        """
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
                logger.info(
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
