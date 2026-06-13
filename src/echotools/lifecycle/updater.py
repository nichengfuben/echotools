from __future__ import annotations

"""自动更新器：检测远端 git 提交并执行 pull。

通用化：重启动作由回调提供，不强制 os._exit。
"""

import asyncio
import os
from pathlib import Path
from typing import Callable, Optional, Tuple

from echotools.logger.manager import get_logger

__all__ = ["AutoUpdater"]

logger = get_logger(__name__)


class AutoUpdater:
    """基于 git 的自动更新器。"""

    def __init__(
        self,
        root: Path,
        branch: str = "main",
        interval: int = 300,
        on_update: Optional[Callable[[], None]] = None,
    ) -> None:
        """初始化更新器。

        Args:
            root: 仓库根目录。
            branch: 跟踪分支。
            interval: 检查间隔（秒）。
            on_update: 更新成功后的回调（如触发重启）。
        """
        self._root = root
        self._branch = branch
        self._interval = interval
        self._running = False
        self._on_update = on_update or self._default_restart

    async def run(self) -> None:
        """启动自动更新循环。"""
        self._running = True
        logger.info(
            "自动更新已启动 (branch=%s, interval=%ds)",
            self._branch,
            self._interval,
        )
        await self._check_and_update()
        while self._running:
            await asyncio.sleep(self._interval)
            try:
                await self._check_and_update()
            except Exception as e:
                logger.warning("自动更新检查异常: %s", e)

    def stop(self) -> None:
        """停止更新循环。"""
        self._running = False
        logger.info("自动更新已停止")

    async def _check_and_update(self) -> None:
        """执行一次检查与更新。"""
        if not self._is_git_repo():
            logger.debug("非 git 仓库，停止自动更新")
            self._running = False
            return
        is_behind, local_hash, remote_hash = await self._is_behind()
        if not is_behind:
            return
        logger.info(
            "检测到新提交: %s -> %s，正在更新",
            (local_hash or "?")[:8],
            (remote_hash or "?")[:8],
        )
        if not await self._pull():
            logger.error("git pull 失败")
            return
        logger.info("更新成功，触发回调")
        self._on_update()

    def _is_git_repo(self) -> bool:
        """检查是否为 git 仓库。"""
        return (self._root / ".git").is_dir()

    async def _run_git(
        self, *args: str, timeout: int = 30
    ) -> Tuple[bool, str, str]:
        """执行 git 命令。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(self._root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()
            return proc.returncode == 0, out, err
        except asyncio.TimeoutError:
            return False, "", "git 超时"
        except FileNotFoundError:
            return False, "", "git 未安装"
        except Exception as e:
            return False, "", str(e)

    async def _is_behind(
        self,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """检查本地是否落后远端。"""
        ok, _, err = await self._run_git("fetch", "origin", self._branch)
        if not ok:
            logger.warning("git fetch 失败: %s", err)
            return False, None, None
        ok, local_hash, _ = await self._run_git("rev-parse", "HEAD")
        if not ok:
            return False, None, None
        ok, remote_hash, _ = await self._run_git(
            "rev-parse", "origin/{}".format(self._branch)
        )
        if not ok:
            return False, local_hash, None
        if local_hash == remote_hash:
            return False, local_hash, remote_hash
        return True, local_hash, remote_hash

    async def _pull(self) -> bool:
        """执行 git pull。"""
        ok, out, _ = await self._run_git("status", "--porcelain")
        if ok and out:
            logger.warning("工作树有改动，暂存中")
            await self._run_git(
                "stash", "push", "-m", "autoupdate stash"
            )
        ok, out, err = await self._run_git(
            "pull", "--ff-only", "origin", self._branch
        )
        if not ok:
            ok, out, err = await self._run_git(
                "pull", "origin", self._branch
            )
            if not ok:
                logger.error("git pull 失败: %s", err)
                return False
        logger.info("git pull 成功: %s", out)
        return True

    @staticmethod
    def _default_restart() -> None:
        """默认重启动作：退出码 42。"""
        os._exit(42)


# ---------------------------------------------------------------------------
# 单例辅助
# ---------------------------------------------------------------------------

_updater: Optional[AutoUpdater] = None


def get_updater() -> Optional[AutoUpdater]:
    """获取全局 AutoUpdater 实例。"""
    return _updater


def set_updater(updater: AutoUpdater) -> None:
    """设置全局 AutoUpdater 实例。"""
    global _updater
    _updater = updater
