from __future__ import annotations

"""调用链上下文管理（基于 contextvars，跨 async 安全）。"""

import contextvars
from typing import Optional

__all__ = [
    "get_current_trace_id",
    "set_current_trace_id",
    "get_current_span_id",
    "set_current_span_id",
    "get_request_id",
    "set_request_id",
    "reset_context",
]

_trace_id_var: "contextvars.ContextVar[Optional[str]]" = (
    contextvars.ContextVar("echo_trace_id", default=None)
)
_span_id_var: "contextvars.ContextVar[Optional[str]]" = (
    contextvars.ContextVar("echo_span_id", default=None)
)
_request_id_var: "contextvars.ContextVar[Optional[str]]" = (
    contextvars.ContextVar("echo_request_id", default=None)
)


def get_current_trace_id() -> Optional[str]:
    """获取当前 trace_id。"""
    return _trace_id_var.get()


def set_current_trace_id(value: Optional[str]) -> "contextvars.Token":
    """设置当前 trace_id，返回可用于重置的 Token。"""
    return _trace_id_var.set(value)


def get_current_span_id() -> Optional[str]:
    """获取当前 span_id。"""
    return _span_id_var.get()


def set_current_span_id(value: Optional[str]) -> "contextvars.Token":
    """设置当前 span_id。"""
    return _span_id_var.set(value)


def get_request_id() -> Optional[str]:
    """获取当前 request_id。"""
    return _request_id_var.get()


def set_request_id(value: Optional[str]) -> "contextvars.Token":
    """设置当前 request_id。"""
    return _request_id_var.set(value)


def reset_context() -> None:
    """重置全部调用链上下文。"""
    _trace_id_var.set(None)
    _span_id_var.set(None)
    _request_id_var.set(None)
