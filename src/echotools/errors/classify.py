from __future__ import annotations

"""HTTP 状态码错误分类。"""

from typing import Optional

from echotools.errors.base import EchoError
from echotools.errors.common import (
    NetworkError,
    NotSupportedError,
    TimeoutError,
    ValidationError,
)

__all__ = ["classify_http_error"]


def classify_http_error(
    status_code: int,
    message: str,
    original: Optional[Exception] = None,
) -> EchoError:
    """根据 HTTP 状态码分类错误。

    Args:
        status_code: HTTP 状态码。
        message: 错误信息。
        original: 原始异常。

    Returns:
        对应的 EchoError 实例。
    """
    if status_code == 400:
        return ValidationError(message)
    if status_code in (408, 504):
        return TimeoutError(message)
    if status_code == 501:
        return NotSupportedError(message)
    if status_code >= 500:
        return NetworkError(message, original=original)
    err = EchoError(message, original=original, status_code=status_code)
    return err
