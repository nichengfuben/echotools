"""Log writer protocol and implementations."""
from __future__ import annotations

import datetime
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol, Tuple, runtime_checkable


@runtime_checkable
class LogWriter(Protocol):
    """日志写入器协议"""

    def write(self, content: str) -> None:
        """写入日志内容"""
        ...


@dataclass
class FileLogWriter:
    """文件日志写入器"""
    file_path: str
    source_name: str = "consoleui"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def write(self, content: str) -> None:
        """线程安全地写入日志文件"""
        try:
            timestamp = datetime.datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f",
            )[:-3]
            with self._lock, open(self.file_path, "a", encoding="utf-8") as f:
                for line in content.splitlines():
                    f.write(f"[{self.source_name}][{timestamp}] {line}\n")
        except OSError:
            pass


class NullLogWriter:
    """空日志写入器（无操作）"""

    def write(self, content: str) -> None:
        """空操作"""


class MultiLogWriter:
    """多路日志写入器"""

    def __init__(self, *writers: LogWriter) -> None:
        self._writers: Tuple[LogWriter, ...] = writers

    def write(self, content: str) -> None:
        """向所有写入器分发日志"""
        for writer in self._writers:
            writer.write(content)


class CallbackLogWriter:
    """回调日志写入器"""

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback

    def write(self, content: str) -> None:
        """通过回调函数写入日志"""
        self._callback(content)

