from __future__ import annotations

"""通用 I/O 工具。"""

import os
import time
from pathlib import Path
from typing import Optional

from echotools.logger.manager import get_logger

__all__ = [
    "atomic_write_text",
    "ensure_directory",
    "read_text_if_exists",
]

logger = get_logger(__name__)


def ensure_directory(path: Path) -> Path:
    """确保目录存在。

    Args:
        path: 目录路径。

    Returns:
        原路径对象。
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(
    path: Path,
    content: str,
    *,
    retries: int = 3,
    encoding: str = "utf-8",
) -> None:
    """原子写入文本文件。

    Args:
        path: 目标路径。
        content: 文本内容。
        retries: PermissionError 重试次数。
        encoding: 编码。
    """
    ensure_directory(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding=encoding)
    for attempt in range(retries):
        try:
            os.replace(str(temp_path), str(path))
            return
        except PermissionError:
            if attempt >= retries - 1:
                break
            time.sleep(0.1 * (attempt + 1))
    path.write_text(content, encoding=encoding)
    try:
        temp_path.unlink()
    except OSError as exc:
        logger.debug("清理临时文件失败: %s", exc)


def read_text_if_exists(
    path: Path, *, encoding: str = "utf-8"
) -> Optional[str]:
    """读取存在的文本文件，不存在返回 None。

    Args:
        path: 文件路径。
        encoding: 编码。

    Returns:
        内容或 None。
    """
    if not path.is_file():
        return None
    return path.read_text(encoding=encoding)
