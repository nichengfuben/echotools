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
        """初始化异常。

        Args:
            message: 错误信息。
            original: 原始异常。
            status_code: 关联状态码。
        """
        super().__init__(message)
        self.message = message
        self.original = original
        self.status_code = status_code
