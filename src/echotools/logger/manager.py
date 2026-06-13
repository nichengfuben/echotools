from __future__ import annotations

"""日志管理器：统一日志输出，可选调用链上下文注入。"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

__all__ = ["LoggerManager", "get_logger", "set_color", "configure"]

_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[35m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """带颜色的格式化器 — 仅着色级别名。"""

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if self._use_color:
            color = _COLORS.get(record.levelname, "")
            if color:
                saved = record.levelname
                record.levelname = "{}{}{}".format(color, saved, _RESET)
                text = super().format(record)
                record.levelname = saved
                return text
        return super().format(record)


class LoggerManager:
    """日志中央管理器。

    支持控制台、文件、轮转、颜色控制。
    """

    _DEFAULT_FMT = (
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d"
        " | %(message)s"
    )
    _DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        self._use_color = False
        self._level = logging.INFO
        self._configured = False
        self._log_file: Optional[Path] = None
        self._fmt = self._DEFAULT_FMT

    def configure(
        self,
        level: str = "INFO",
        color: bool = False,
        log_file: Optional[str] = None,
        fmt: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        """配置全局日志。

        Args:
            level: 日志级别。
            color: 是否启用颜色（默认 False）。
            log_file: 日志文件路径。
            fmt: 自定义格式。
            max_bytes: 单文件最大字节。
            backup_count: 保留文件数。
        """
        self._use_color = color
        self._level = getattr(logging, level.upper(), logging.INFO)
        self._fmt = fmt or self._DEFAULT_FMT
        if log_file is not None:
            self._log_file = Path(log_file)

        root = logging.getLogger()
        root.setLevel(self._level)
        root.handlers.clear()

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(
            _ColorFormatter(self._fmt, self._DEFAULT_DATEFMT, self._use_color)
        )
        root.addHandler(console)

        if self._log_file is not None:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                filename=str(self._log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setFormatter(
                _ColorFormatter(self._fmt, self._DEFAULT_DATEFMT, False)
            )
            root.addHandler(fh)

        self._configured = True

    def set_color(self, enabled: bool) -> None:
        """切换颜色开关。"""
        self._use_color = enabled
        for handler in logging.getLogger().handlers:
            fmtr = handler.formatter
            if isinstance(fmtr, _ColorFormatter):
                fmtr._use_color = enabled and not isinstance(
                    handler, logging.handlers.RotatingFileHandler
                )

    def get_logger(self, name: str) -> logging.Logger:
        """获取命名 logger，直接使用传入的 name。"""
        if not self._configured:
            self.configure()
        return logging.getLogger(name)


_manager = LoggerManager()


def configure(**kwargs: object) -> None:
    """配置全局日志。"""
    _manager.configure(**kwargs)  # type: ignore[arg-type]


def get_logger(name: str) -> logging.Logger:
    """获取 logger。"""
    return _manager.get_logger(name)


def set_color(enabled: bool) -> None:
    """切换颜色。"""
    _manager.set_color(enabled)
