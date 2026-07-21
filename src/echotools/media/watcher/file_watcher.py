from __future__ import annotations

"""文件变更监视器：轮询式，跨平台无依赖。

完全通用：通过回调上报变更，不预设重启/热重载逻辑。
"""

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Set, Union

from echotools.base.logger.manager import get_logger

__all__ = ["FileWatcher"]

logger = get_logger(__name__)

ChangeCallback = Callable[[Set[str]], Awaitable[None]]


class FileWatcher:
    """轮询式文件监视器。

    监视指定目录/文件，变更时回调，不绑定任何业务逻辑。
    """

    def __init__(
        self,
        paths: List[Union[str, Path]],
        *,
        extensions: Optional[Set[str]] = None,
        interval: float = 2.0,
    ) -> None:
        """初始化监视器。

        Args:
            paths: 监视的文件或目录路径列表（str 或 Path）。
            extensions: 仅监视的扩展名集合（含点），None 表示全部。
            interval: 轮询间隔（秒）。
        """
        self._paths = [Path(p) for p in paths]
        self._extensions = extensions
        self._interval = interval
        self._mtimes: Dict[str, float] = {}
        self._running = False
        self._callback: Optional[ChangeCallback] = None

    def _scan(self) -> Dict[str, float]:
        """扫描所有被监视文件的修改时间。"""
        result: Dict[str, float] = {}
        for base in self._paths:
            if base.is_dir():
                for p in base.rglob("*"):
                    if not p.is_file():
                        continue
                    if (
                        self._extensions is not None
                        and p.suffix not in self._extensions
                    ):
                        continue
                    try:
                        result[str(p)] = p.stat().st_mtime
                    except OSError as e:
                        logger.debug("扫描 %s 失败: %s", p, e)
            elif base.is_file():
                try:
                    result[str(base)] = base.stat().st_mtime
                except OSError as e:
                    logger.debug("扫描 %s 失败: %s", base, e)
        return result

    async def start(self, callback: ChangeCallback) -> None:
        """启动监视循环。

        Args:
            callback: 变更回调，接收变更文件路径集合。
        """
        self._callback = callback
        self._running = True
        self._mtimes = self._scan()
        logger.debug("文件监视已启动: %s", [str(p) for p in self._paths])
        while self._running:
            await asyncio.sleep(self._interval)
            try:
                await self._check()
            except Exception as e:
                logger.warning("文件监视检查失败: %s", e)

    async def _check(self) -> None:
        """执行一次变更检查。"""
        current = self._scan()
        changed: Set[str] = set()
        for fp, mt in current.items():
            if fp not in self._mtimes or self._mtimes[fp] != mt:
                changed.add(fp)
        removed = set(self._mtimes) - set(current)
        changed.update(removed)
        self._mtimes = current
        if not changed:
            return
        logger.debug(
            "检测到文件变更: %s", [Path(f).name for f in changed]
        )
        if self._callback is not None:
            await self._callback(changed)

    def stop(self) -> None:
        """停止监视。"""
        self._running = False
        logger.debug("文件监视已停止")
