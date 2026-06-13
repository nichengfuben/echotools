from __future__ import annotations

"""HTTP 状态码错误分类——含上下文长度检测。"""

from typing import Optional

from echotools.errors.base import EchoError
from echotools.errors.common import (
    NetworkError,
    NotSupportedError,
    TimeoutError,
    ValidationError,
)
from echotools.errors.http import (
    AuthError,
    ContextLengthError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)

__all__ = ["classify_http_error"]

_CONTEXT_KEYWORDS = (
    "context",
    "token",
    "max_tokens",
    "maximum context",
    "prompt is too long",
    "上下文",
    "超长",
    "超出",
)


def classify_http_error(
    status_code: int,
    message: str,
    original: Optional[Exception] = None,
) -> EchoError:
    """根据 HTTP 状态码分类错误。

    支持的特殊检测：
    - 400 + 上下文关键词 → ContextLengthError
    - 401 → AuthError
    - 402 → QuotaExceededError
    - 404 → NotFoundError
    - 429 → RateLimitError
    - 5xx → ServerError

    Args:
        status_code: HTTP 状态码。
        message: 错误信息。
        original: 原始异常。

    Returns:
        对应的 EchoError 实例。
    """
    if status_code == 400:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in _CONTEXT_KEYWORDS):
            return ContextLengthError(message, original=original)
        return ValidationError(message)
    if status_code == 401:
        return AuthError(message, original=original)
    if status_code == 402:
        return QuotaExceededError(message, original=original)
    if status_code == 404:
        return NotFoundError(message, original=original)
    if status_code in (408, 504):
        return TimeoutError(message)
    if status_code == 429:
        return RateLimitError(message, original=original)
    if status_code == 501:
        return NotSupportedError(message)
    if status_code >= 500:
        return ServerError(message, http_status=status_code, original=original)
    err = EchoError(message, original=original, status_code=status_code)
    return err
