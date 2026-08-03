from __future__ import annotations

"""事件总线：支持同步与异步订阅者。"""

import asyncio
import inspect
from collections import defaultdict
from typing import Awaitable, Callable, DefaultDict, List, Type, Union

from echotools.base.logger.manager import get_logger
from echotools.media.events.event import Event

__all__ = ["EventBus"]

logger = get_logger(__name__)

Handler = Callable[[Event], Union[None, Awaitable[None]]]


class EventBus:
    """按事件类型订阅；同步/异步回调统一调度，单 handler 异常不影响其余。"""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[Type[Event], List[Handler]] = (
            defaultdict(list)
        )

    def subscribe(self, event_type: Type[Event], handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[Event], handler: Handler) -> None:
        handlers = self._subscribers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def publish_sync(self, event: Event) -> None:
        """同步发布；异步 handler 被跳过。"""
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
        self._subscribers.clear()
