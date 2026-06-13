from __future__ import annotations

"""错误模块统一导出。"""

from echotools.errors.base import EchoError
from echotools.errors.classify import classify_http_error
from echotools.errors.common import (
    ConfigError,
    NetworkError,
    NoCandidateError,
    NotSupportedError,
    PluginError,
    ProtocolError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "EchoError",
    "ConfigError",
    "ValidationError",
    "NetworkError",
    "TimeoutError",
    "NotSupportedError",
    "NoCandidateError",
    "PluginError",
    "ProtocolError",
    "classify_http_error",
]
