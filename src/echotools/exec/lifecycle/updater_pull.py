from __future__ import annotations

from typing import Any, Tuple

from echotools.base.logger.manager import get_logger

logger = get_logger(__name__)


async def abort_in_progress_merge(updater: Any) -> None:
    ok, out, _ = await updater._run_git("status", "--porcelain")
    if not ok:
        return
    if not any(
        line.startswith(("UU", "AA", "DD", "AU", "UA", "DU", "UD"))
        for line in out.splitlines()
    ):
        return
    logger.warning("检测到未完成的合并，正在中止")
    await updater._run_git("merge", "--abort")


async def stash_if_dirty(updater: Any) -> bool:
    ok, out, _ = await updater._run_git("status", "--porcelain")
    if not ok or not out:
        return False
    logger.warning("工作树有改动，暂存中")
    ok_s, _, _ = await updater._run_git("stash", "push", "-m", "autoupdate stash")
    return ok_s


async def try_fast_forward_pull(updater: Any) -> Tuple[bool, str, str]:
    return await updater._run_git("pull", "--ff-only", "origin", updater._branch)
