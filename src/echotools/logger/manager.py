from __future__ import annotations

"""日志管理器 — 匹配 src.logger (loguru) 的输出格式。"""

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

_LEVEL_LETTERS = {
    "DEBUG": "D",
    "INFO": "I",
    "WARNING": "W",
    "ERROR": "E",
    "CRITICAL": "C",
}


class _LogFormatter(logging.Formatter):
    """匹配 src.logger 格式: MM-DD HH:MM:SS | [ X ] | name | message"""

    def __init__(self, datefmt: str, use_color: bool) -> None:
        super().__init__(datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        # Format timestamp
        record.asctime = self.formatTime(record, self.datefmt)

        # Level letter
        letter = _LEVEL_LETTERS.get(record.levelname, "?")
        level_str = "[ {} ]".format(letter)

        # Color
        if self._use_color:
            color = _COLORS.get(record.levelname, "")
            if color:
                level_str = "{}{}{}".format(color, level_str, _RESET)

        # Build line: MM-DD HH:MM:SS | [ X ] | name | message
        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = msg + "\n" + record.exc_text

        return "{} | {} | {} | {}".format(
            record.asctime, level_str, record.name, msg
        )


class LoggerManager:
    """日志中央管理器。"""

    _DEFAULT_DATEFMT = "%m-%d %H:%M:%S"

    def __init__(self) -> None:
        self._use_color = False
        self._level = logging.INFO
        self._configured = False
        self._log_file: Optional[Path] = None

    def configure(
        self,
        level: str = "INFO",
        color: bool = False,
        log_file: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        **kwargs,
    ) -> None:
        """配置全局日志。"""
        self._use_color = color
        self._level = getattr(logging, level.upper(), logging.INFO)
        if log_file is not None:
            self._log_file = Path(log_file)

        root = logging.getLogger()
        root.setLevel(self._level)
        root.handlers.clear()

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(
            _LogFormatter(self._DEFAULT_DATEFMT, self._use_color)
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
                _LogFormatter(self._DEFAULT_DATEFMT, False)
            )
            root.addHandler(fh)

        self._configured = True

    def set_color(self, enabled: bool) -> None:
        """切换颜色开关。"""
        self._use_color = enabled
        for handler in logging.getLogger().handlers:
            fmtr = handler.formatter
            if isinstance(fmtr, _LogFormatter):
                fmtr._use_color = enabled and not isinstance(
                    handler, logging.handlers.RotatingFileHandler
                )

    def get_logger(self, name: str) -> logging.Logger:
        """获取命名 logger。"""
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
