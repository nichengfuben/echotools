from __future__ import annotations

"""生命周期管理器：启动/关闭钩子，资源编排。"""

import asyncio
from typing import Awaitable, Callable, List, Union

from echotools.base.logger.manager import get_logger

__all__ = ["LifecycleManager"]

logger = get_logger(__name__)

Hook = Callable[[], Union[None, Awaitable[None]]]


class LifecycleManager:
    """应用生命周期管理器。

    管理启动与关闭钩子，按注册顺序执行启动，逆序执行关闭。
    """

    def __init__(self) -> None:
        """初始化管理器。"""
        self._startup_hooks: List[Hook] = []
        self._shutdown_hooks: List[Hook] = []
        self._started = False

    def on_startup(self, hook: Hook) -> Hook:
        """注册启动钩子（可作装饰器）。"""
        self._startup_hooks.append(hook)
        return hook

    def on_shutdown(self, hook: Hook) -> Hook:
        """注册关闭钩子（可作装饰器）。"""
        self._shutdown_hooks.append(hook)
        return hook

    async def startup(self) -> None:
        """执行全部启动钩子。"""
        if self._started:
            return
        logger.debug("生命周期启动，执行 %d 个钩子", len(self._startup_hooks))
        for hook in self._startup_hooks:
            await self._run(hook)
        self._started = True

    async def shutdown(self) -> None:
        """逆序执行全部关闭钩子。"""
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
        """执行单个钩子，兼容同步/异步。"""
        result = hook()
        if asyncio.iscoroutine(result):
            await result

    @property
    def started(self) -> bool:
        """是否已启动。"""
        return self._started
