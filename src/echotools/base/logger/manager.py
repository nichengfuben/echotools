from __future__ import annotations

"""日志管理器 — 通用日志基础设施，支持彩色终端输出。"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

__all__ = ["LoggerManager", "get_logger", "set_color", "configure"]

_BOLD = "\033[1m"
_COLORS = {
    "DEBUG": "\033[34m" + _BOLD,
    "INFO": _BOLD,
    "WARNING": "\033[33m" + _BOLD,
    "ERROR": "\033[31m" + _BOLD,
    "CRITICAL": "\033[35m" + _BOLD,
}
_BLUE = "\033[34m"
_CYAN = "\033[36m"
_RESET = "\033[0m"

_LEVEL_LETTERS = {
    "DEBUG": "D",
    "INFO": "I",
    "WARNING": "W",
    "ERROR": "E",
    "CRITICAL": "C",
}


def _supports_color() -> bool:
    """检测终端是否支持 ANSI 颜色输出。

    检测顺序：
    1. NO_COLOR → 禁用
    2. FORCE_COLOR / CLICOLOR_FORCE → 启用
    3. TERM 环境变量（xterm, msys, cygwin 等）→ 启用
    4. Windows Terminal (WT_SESSION) / ANSICON → 启用
    5. sys.stdout.isatty() → 启用
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
        return True
    term = os.environ.get("TERM", "")
    if term and term != "dumb":
        return True
    if sys.platform == "win32":
        if "WT_SESSION" in os.environ:
            return True
        if os.environ.get("ANSICON"):
            return True
    return sys.stdout.isatty()


class _LogFormatter(logging.Formatter):
    """通用日志格式化器，支持可选 ANSI 彩色输出。

    输出格式: MM-DD HH:MM:SS | [ X ] | name | message
    彩色模式: 时间戳(蓝) | 等级(按级别着色) | 模块名(青) | 消息(按级别着色)
    """

    def __init__(self, datefmt: str, use_color: bool) -> None:
        super().__init__(datefmt=datefmt)
        self._use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = self.formatTime(record, self.datefmt)

        letter = _LEVEL_LETTERS.get(record.levelname, "?")
        level_str = "[ {} ]".format(letter)

        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = msg + "\n" + record.exc_text

        if self._use_color:
            level_color = _COLORS.get(record.levelname, "")
            ts = "{}{}{}".format(_BLUE, record.asctime, _RESET)
            if level_color:
                level_str = "{}{}{}".format(level_color, level_str, _RESET)
            name_str = "{}{}{}".format(_CYAN, record.name, _RESET)
            msg_str = "{}{}{}".format(level_color, msg, _RESET) if level_color else msg
            return "{} | {} | {} | {}".format(ts, level_str, name_str, msg_str)

        return "{} | {} | {} | {}".format(
            record.asctime, level_str, record.name, msg
        )


class LoggerManager:
    """日志中央管理器。"""

    _DEFAULT_DATEFMT = "%m-%d %H:%M:%S"

    def __init__(self) -> None:
        self._color_wanted = False
        self._use_color = False
        self._level = logging.INFO
        self._configured = False
        self._log_file: Optional[Path] = None

    def _resolve_color(self, wanted: bool) -> bool:
        return wanted and _supports_color()

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
        self._color_wanted = color
        self._use_color = self._resolve_color(color)
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
        self._color_wanted = enabled
        actual = self._resolve_color(enabled)
        self._use_color = actual
        for handler in logging.getLogger().handlers:
            fmtr = handler.formatter
            if isinstance(fmtr, _LogFormatter):
                fmtr._use_color = actual and not isinstance(
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
