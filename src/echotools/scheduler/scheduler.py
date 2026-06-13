from __future__ import annotations

"""任务调度器：并发限制 + 任务追踪。"""

import asyncio
from typing import Any, Awaitable, Dict

from echotools.logger.manager import get_logger

__all__ = ["TaskScheduler"]

logger = get_logger(__name__)


class TaskScheduler:
    """带并发限制的任务调度器。"""

    def __init__(self, max_concurrent: int = 3) -> None:
        """初始化调度器。

        Args:
            max_concurrent: 最大并发数。
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: Dict[str, "asyncio.Task[Any]"] = {}
        self._max_concurrent = max_concurrent

    async def submit(self, task_id: str, coro: Awaitable[Any]) -> Any:
        """提交任务并等待结果。

        Args:
            task_id: 任务标识。
            coro: 协程对象。

        Returns:
            任务结果。

        Raises:
            任务执行异常。
        """
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
        """取消所有活跃任务。"""
        for task_id, task in list(self._active_tasks.items()):
            logger.debug("取消任务: %s", task_id)
            task.cancel()
        self._active_tasks.clear()

    def get_status(self) -> Dict[str, Any]:
        """获取调度状态。

        Returns:
            状态字典。
        """
        return {
            "max_concurrent": self._max_concurrent,
            "active_count": len(self._active_tasks),
            "active_tasks": list(self._active_tasks.keys()),
        }
