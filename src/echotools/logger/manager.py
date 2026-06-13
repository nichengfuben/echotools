from __future__ import annotations

"""日志管理器：统一日志输出，自动注入调用链上下文。"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from echotools.tracing.context import (
    get_current_span_id,
    get_current_trace_id,
    get_request_id,
)

__all__ = ["LoggerManager", "get_logger", "set_color", "configure"]

_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
_RESET = "\033[0m"


class _TraceFilter(logging.Filter):
    """注入调用链上下文到日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_current_trace_id() or "-"
        record.span_id = get_current_span_id() or "-"
        record.request_id = get_request_id() or "-"
        return True


class _ColorFormatter(logging.Formatter):
    """带颜色的格式化器。"""

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if self._use_color:
            color = _COLORS.get(record.levelname, "")
            if color:
                return "{}{}{}".format(color, text, _RESET)
        return text


class LoggerManager:
    """日志中央管理器。

    支持控制台、文件、轮转、颜色、JSON、调用链注入。
    """

    _DEFAULT_FMT = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d "
        "| trace=%(trace_id)s span=%(span_id)s | %(message)s"
    )
    _DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        """初始化管理器。"""
        self._use_color = True
        self._level = logging.INFO
        self._configured = False
        self._log_file: Optional[Path] = None
        self._fmt = self._DEFAULT_FMT

    def configure(
        self,
        level: str = "INFO",
        color: bool = True,
        log_file: Optional[str] = None,
        fmt: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        """配置全局日志。

        Args:
            level: 日志级别。
            color: 是否启用颜色。
            log_file: 日志文件路径，None 表示仅控制台。
            fmt: 自定义格式。
            max_bytes: 单文件最大字节。
            backup_count: 保留文件数。
        """
        self._use_color = color
        self._level = getattr(logging, level.upper(), logging.INFO)
        self._fmt = fmt or self._DEFAULT_FMT
        if log_file is not None:
            self._log_file = Path(log_file)

        root = logging.getLogger("echotools")
        root.setLevel(self._level)
        root.handlers.clear()
        root.propagate = False

        trace_filter = _TraceFilter()

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(
            _ColorFormatter(self._fmt, self._DEFAULT_DATEFMT, self._use_color)
        )
        console.addFilter(trace_filter)
        root.addHandler(console)

        if self._log_file is not None:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                filename=str(self._log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(
                _ColorFormatter(self._fmt, self._DEFAULT_DATEFMT, False)
            )
            file_handler.addFilter(trace_filter)
            root.addHandler(file_handler)

        self._configured = True

    def set_color(self, enabled: bool) -> None:
        """切换颜色开关。"""
        self._use_color = enabled
        for handler in logging.getLogger("echotools").handlers:
            fmtr = handler.formatter
            if isinstance(fmtr, _ColorFormatter):
                fmtr._use_color = enabled and not isinstance(
                    handler, logging.handlers.RotatingFileHandler
                )

    def get_logger(self, name: str) -> logging.Logger:
        """获取命名 logger。"""
        if not self._configured:
            self.configure()
        if not name.startswith("echotools"):
            name = "echotools.{}".format(name)
        return logging.getLogger(name)


_manager = LoggerManager()


def configure(**kwargs: object) -> None:
    """配置全局日志（模块级快捷方式）。"""
    _manager.configure(**kwargs)  # type: ignore[arg-type]


def get_logger(name: str) -> logging.Logger:
    """获取 logger（模块级快捷方式）。"""
    return _manager.get_logger(name)


def set_color(enabled: bool) -> None:
    """切换颜色（模块级快捷方式）。"""
    _manager.set_color(enabled)
