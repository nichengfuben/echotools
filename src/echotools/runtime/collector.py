from __future__ import annotations

"""运行时视图聚合（通用版本）。"""

import time
from typing import Any, Callable, Dict

from echotools.logger.manager import get_logger

__all__ = ["RuntimeCollector"]

logger = get_logger(__name__)


class RuntimeCollector:
    """运行时摘要收集器。

    通过注册的 collector 回调聚合系统状态，完全项目无关。
    """

    def __init__(self, service_name: str = "echotools") -> None:
        """初始化收集器。

        Args:
            service_name: 服务名。
        """
        self._service_name = service_name
        self._collectors: Dict[str, Callable[[], Any]] = {}

    def register(self, name: str, collector: Callable[[], Any]) -> None:
        """注册状态收集器。

        Args:
            name: 段名。
            collector: 同步回调，返回该段数据。
        """
        self._collectors[name] = collector

    async def collect(self) -> Dict[str, Any]:
        """收集运行时摘要。

        Returns:
            摘要字典。
        """
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
