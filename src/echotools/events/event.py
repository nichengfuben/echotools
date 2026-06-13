from __future__ import annotations

"""事件基类。"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict

__all__ = ["Event"]


@dataclass
class Event:
    """事件基类。

    用户继承此类定义具体事件，dataclass 字段即事件载荷。
    """

    timestamp: float = field(default_factory=time.time, init=False)

    @property
    def name(self) -> str:
        """事件名称（默认为类名）。"""
        return type(self).__name__

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        result: Dict[str, Any] = {"event": self.name}
        for key, value in self.__dict__.items():
            result[key] = value
        return result
