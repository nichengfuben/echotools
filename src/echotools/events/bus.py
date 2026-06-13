from __future__ import annotations

"""事件总线：支持同步与异步订阅者。"""

import asyncio
import inspect
from collections import defaultdict
from typing import Any, Awaitable, Callable, DefaultDict, List, Type, Union

from echotools.events.event import Event
from echotools.logger.manager import get_logger

__all__ = ["EventBus"]

logger = get_logger(__name__)

Handler = Callable[[Event], Union[None, Awaitable[None]]]


class EventBus:
    """事件总线。

    支持按事件类型订阅，同步/异步回调统一调度，异常隔离。
    """

    def __init__(self) -> None:
        """初始化总线。"""
        self._subscribers: DefaultDict[Type[Event], List[Handler]] = (
            defaultdict(list)
        )

    def subscribe(self, event_type: Type[Event], handler: Handler) -> None:
        """订阅事件。

        Args:
            event_type: 事件类型。
            handler: 同步或异步回调。
        """
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[Event], handler: Handler) -> None:
        """取消订阅。"""
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def publish_sync(self, event: Event) -> None:
        """同步发布事件，仅触发同步回调，异步回调被跳过。

        Args:
            event: 事件实例。
        """
        for handler in list(self._subscribers.get(type(event), [])):
            if inspect.iscoroutinefunction(handler):
                logger.debug("同步发布跳过异步处理器: %s", handler)
                continue
            try:
                handler(event)
            except Exception as exc:
                logger.error(
                    "事件处理器异常 [%s]: %s",
                    event.name,
                    exc,
                    exc_info=True,
                )

    async def publish(self, event: Event) -> None:
        """异步发布事件，并发触发全部回调。

        Args:
            event: 事件实例。
        """
        coros: List[Awaitable[None]] = []
        for handler in list(self._subscribers.get(type(event), [])):
            try:
                if inspect.iscoroutinefunction(handler):
                    coros.append(self._safe_async(handler, event))
                else:
                    handler(event)
            except Exception as exc:
                logger.error(
                    "事件处理器异常 [%s]: %s",
                    event.name,
                    exc,
                    exc_info=True,
                )
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _safe_async(self, handler: Handler, event: Event) -> None:
        """包裹异步处理器，隔离异常。"""
        try:
            await handler(event)  # type: ignore[misc]
        except Exception as exc:
            logger.error(
                "异步事件处理器异常 [%s]: %s",
                event.name,
                exc,
                exc_info=True,
            )

    def clear(self) -> None:
        """清空所有订阅。"""
        self._subscribers.clear()
