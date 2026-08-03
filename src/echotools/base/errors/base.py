from __future__ import annotations

"""基础异常类。"""

from typing import Optional

__all__ = ["EchoError"]


class EchoError(Exception):
    """echotools 根异常。

    所有 SDK 异常的基类，携带状态码与原始异常。
    """

    def __init__(
        self,
        message: str,
        original: Optional[Exception] = None,
        status_code: int = 500,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.original = original
        self.status_code = status_code
