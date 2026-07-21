from __future__ import annotations

"""Web module exports."""

from typing import Any

from echotools.media.web.stats import RequestStats, get_stats
from echotools.media.web.utils import clean_fncall, json_body, safe_flush

__all__ = [
    "WebApplication",
    "json_body",
    "safe_flush",
    "clean_fncall",
    "RequestStats",
    "get_stats",
    "RequestBroker",
    "request_broker",
    "create_stats_middleware",
]

_LAZY_EXPORTS = {
    "WebApplication": ("echotools.media.web.application", "WebApplication"),
    "RequestBroker": ("echotools.media.web.broker", "RequestBroker"),
    "request_broker": ("echotools.media.web.broker", "request_broker"),
    "create_stats_middleware": ("echotools.media.web.middleware", "create_stats_middleware"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_path, attr = _LAZY_EXPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
