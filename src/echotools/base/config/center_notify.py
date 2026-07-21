from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List

from echotools.base.logger.manager import get_logger

logger = get_logger(__name__)


async def notify_config_changes(
    callbacks: Dict[str, List[Callable[[Any, Any], Any]]],
    old: Dict[str, Any],
    new: Dict[str, Any],
    dig_fn: Callable[[Dict[str, Any], str], Any],
) -> None:
    for path, cbs in callbacks.items():
        old_val = dig_fn(old, path)
        new_val = dig_fn(new, path)
        if old_val == new_val:
            continue
        logger.debug("配置变更: %s", path)
        await _invoke_callbacks(path, cbs, old_val, new_val)


async def _invoke_callbacks(
    path: str,
    callbacks: List[Callable[[Any, Any], Any]],
    old_val: Any,
    new_val: Any,
) -> None:
    for cb in callbacks:
        try:
            if asyncio.iscoroutinefunction(cb):
                await cb(old_val, new_val)
            else:
                cb(old_val, new_val)
        except Exception as exc:
            logger.error("配置回调异常 [%s]: %s", path, exc, exc_info=True)
