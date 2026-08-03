from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Dict

from echotools.base.logger.manager import get_logger

__all__ = ["TaskScheduler"]

logger = get_logger(__name__)


class TaskScheduler:
    """带并发上限的 asyncio 任务调度。"""

    def __init__(self, max_concurrent: int = 3) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: Dict[str, "asyncio.Task[Any]"] = {}
        self._max_concurrent = max_concurrent

    async def submit(self, task_id: str, coro: Awaitable[Any]) -> Any:
        async with self._semaphore:
            task = asyncio.ensure_future(coro)
            self._active_tasks[task_id] = task
            try:
                return await task
            except Exception as e:
                logger.error("任务 %s 失败: %s", task_id, e)
                raise
            finally:
                self._active_tasks.pop(task_id, None)

    async def cancel_all(self) -> None:
        for task_id, task in list(self._active_tasks.items()):
            logger.debug("取消任务: %s", task_id)
            task.cancel()
        self._active_tasks.clear()

    def get_status(self) -> Dict[str, Any]:
        return {
            "max_concurrent": self._max_concurrent,
            "active_count": len(self._active_tasks),
            "active_tasks": list(self._active_tasks.keys()),
        }
