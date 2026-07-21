from __future__ import annotations

"""插件基类协议。"""

from abc import ABC, abstractmethod
from typing import Any, Dict

__all__ = ["Plugin"]


class Plugin(ABC):
    """插件基类。

    所有插件实现 name/startup/shutdown，可选 capabilities。
    SDK 不关心插件具体业务（AI/支付/数据库均可）。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """插件唯一名称。"""
        ...

    @abstractmethod
    async def startup(self, context: Any = None) -> None:
        """插件启动。

        Args:
            context: 可选的共享上下文（如 session）。
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """插件关闭，释放资源。"""
        ...

    @property
    def capabilities(self) -> Dict[str, bool]:
        """插件能力声明。"""
        return {}
