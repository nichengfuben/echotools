from __future__ import annotations

import time
from typing import Any, Callable, Dict

from echotools.base.logger.manager import get_logger

__all__ = ["RuntimeCollector"]

logger = get_logger(__name__)


class RuntimeCollector:
    """通过注册的 collector 回调聚合运行时摘要。"""

    def __init__(self, service_name: str = "echotools") -> None:
        self._service_name = service_name
        self._collectors: Dict[str, Callable[[], Any]] = {}

    def register(self, name: str, collector: Callable[[], Any]) -> None:
        self._collectors[name] = collector

    async def collect(self) -> Dict[str, Any]:
        import asyncio

        result: Dict[str, Any] = {
            "service": self._service_name,
            "timestamp": int(time.time()),
        }
        for name, collector in self._collectors.items():
            try:
                value = collector()
                if asyncio.iscoroutine(value):
                    value = await value
                result[name] = value
            except Exception as exc:
                logger.warning("收集 [%s] 失败: %s", name, exc)
                result[name] = {"error": str(exc)}
        return result
