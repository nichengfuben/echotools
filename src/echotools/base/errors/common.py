from __future__ import annotations

"""通用业务异常族。"""

from typing import Optional

from echotools.base.errors.base import EchoError

__all__ = [
    "ConfigError",
    "ValidationError",
    "NetworkError",
    "TimeoutError",
    "NotSupportedError",
    "NoCandidateError",
    "PluginError",
    "ProtocolError",
]


class ConfigError(EchoError):
    """配置错误。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


class ValidationError(EchoError):
    """验证错误。"""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message, status_code=400)
        self.field = field


class NetworkError(EchoError):
    """网络错误。"""

    def __init__(
        self, message: str, original: Optional[Exception] = None
    ) -> None:
        super().__init__(message, original=original, status_code=502)


class TimeoutError(EchoError):  # noqa: A001 - 故意覆盖语义
    """超时错误。"""

    def __init__(self, message: str = "操作超时") -> None:
        super().__init__(message, status_code=504)


class NotSupportedError(EchoError):
    """功能不支持。"""

    def __init__(self, feature: str) -> None:
        super().__init__(
            "{} 功能当前不支持".format(feature), status_code=501
        )
        self.feature = feature


class NoCandidateError(EchoError):
    """无可用候选项。"""

    def __init__(self, message: str = "无可用候选项") -> None:
        super().__init__(message, status_code=503)


class PluginError(EchoError):
    """插件错误。"""


class ProtocolError(EchoError):
    """协议错误。"""
