from __future__ import annotations

"""HTTP 状态码相关的通用异常类。

适用于 API 网关、代理等 HTTP 服务场景。
"""

from typing import Optional

from echotools.base.errors.base import EchoError

__all__ = [
    "HttpError",
    "AuthError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "QuotaExceededError",
    "ContextLengthError",
    "ServerError",
    "StreamError",
]


class HttpError(EchoError):
    """HTTP 错误基类。"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, original=original, status_code=status_code)


class AuthError(HttpError):
    """认证失败 (401)。"""

    def __init__(
        self,
        message: str = "认证失败",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=401, original=original)


class ForbiddenError(HttpError):
    """权限不足 (403)。"""

    def __init__(
        self,
        message: str = "权限不足",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=403, original=original)


class NotFoundError(HttpError):
    """资源不存在 (404)。"""

    def __init__(
        self,
        message: str = "资源不存在",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=404, original=original)


class RateLimitError(HttpError):
    """速率限制 (429)。"""

    def __init__(
        self,
        message: str = "请求频率超限",
        retry_after: Optional[float] = None,
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=429, original=original)
        self.retry_after = retry_after


class QuotaExceededError(HttpError):
    """配额耗尽 (402)。"""

    def __init__(
        self,
        message: str = "配额已耗尽",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=402, original=original)


class ContextLengthError(HttpError):
    """上下文长度超限 (400)。"""

    def __init__(
        self,
        message: str = "输入超过最大上下文长度",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=400, original=original)


class ServerError(HttpError):
    """服务器错误 (5xx)。"""

    def __init__(
        self,
        message: str = "服务器错误",
        http_status: int = 500,
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=http_status, original=original)
        self.http_status = http_status


class StreamError(HttpError):
    """流式响应错误。"""

    def __init__(
        self,
        message: str = "流式响应中断",
        original: Optional[Exception] = None,
    ) -> None:
        super().__init__(message, status_code=502, original=original)
