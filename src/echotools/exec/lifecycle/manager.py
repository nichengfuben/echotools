from __future__ import annotations

"""生命周期管理器：启动/关闭钩子，资源编排。"""

import asyncio
from typing import Awaitable, Callable, List, Union

from echotools.base.logger.manager import get_logger

__all__ = ["LifecycleManager"]

logger = get_logger(__name__)

Hook = Callable[[], Union[None, Awaitable[None]]]


class LifecycleManager:
    """启动钩子正序、关闭钩子逆序执行。"""

    def __init__(self) -> None:
        self._startup_hooks: List[Hook] = []
        self._shutdown_hooks: List[Hook] = []
        self._started = False

    def on_startup(self, hook: Hook) -> Hook:
        self._startup_hooks.append(hook)
        return hook

    def on_shutdown(self, hook: Hook) -> Hook:
        self._shutdown_hooks.append(hook)
        return hook

    async def startup(self) -> None:
        if self._started:
            return
        logger.debug("生命周期启动，执行 %d 个钩子", len(self._startup_hooks))
        for hook in self._startup_hooks:
            await self._run(hook)
        self._started = True

    async def shutdown(self) -> None:
        if not self._started:
            return
        logger.debug(
            "生命周期关闭，执行 %d 个钩子", len(self._shutdown_hooks)
        )
        for hook in reversed(self._shutdown_hooks):
            try:
                await self._run(hook)
            except Exception as exc:
                logger.error("关闭钩子异常: %s", exc, exc_info=True)
        self._started = False

    @staticmethod
    async def _run(hook: Hook) -> None:
        result = hook()
        if asyncio.iscoroutine(result):
            await result

    @property
    def started(self) -> bool:
        return self._started
