from __future__ import annotations

"""错误模块统一导出。"""

from echotools.base.errors.base import EchoError
from echotools.base.errors.classify import classify_http_error
from echotools.base.errors.common import (
    ConfigError,
    NetworkError,
    NoCandidateError,
    NotSupportedError,
    PluginError,
    ProtocolError,
    TimeoutError,
    ValidationError,
)
from echotools.base.errors.http import (
    AuthError,
    ContextLengthError,
    ForbiddenError,
    HttpError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
    StreamError,
)

__all__ = [
    "EchoError",
    "HttpError",
    "ConfigError",
    "ValidationError",
    "NetworkError",
    "TimeoutError",
    "NotSupportedError",
    "NoCandidateError",
    "PluginError",
    "ProtocolError",
    "AuthError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "QuotaExceededError",
    "ContextLengthError",
    "ServerError",
    "StreamError",
    "classify_http_error",
]
