from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from echotools.base.config.loader import (
    find_config,
    find_template,
    load_file,
    write_toml,
)
from echotools.base.config.merge import merge_dicts
from echotools.base.errors.common import ConfigError
from echotools.base.logger.manager import get_logger

if TYPE_CHECKING:
    from echotools.base.config.center import ConfigCenter

logger = get_logger(__name__)
_MISSING = object()


def init_from_template(
    center: "ConfigCenter",
    *,
    filename: str = "config.toml",
    template_dir: str = "template",
    template_name: str = "template_config.toml",
    version_path: str = "server.version",
    exit_after_create: bool = True,
    exit_after_merge: bool = True,
) -> Dict[str, Any]:
    center._path = find_config(filename)
    if center._path is None:
        tpl = find_template(template_dir, template_name)
        if tpl is None:
            raise ConfigError(
                "未找到配置或模板: {}/{}".format(template_dir, template_name)
            )
        target = Path.cwd() / filename
        shutil.copy2(str(tpl), str(target))
        center._path = target
        logger.debug("从模板创建配置: %s", target)
        if exit_after_create:
            raise SystemExit(0)
    center._raw = load_file(center._path)
    try_merge_template(
        center, template_dir, template_name, version_path, exit_after_merge
    )
    logger.debug("配置已加载: %s", center._path)
    return dict(center._raw)


def try_merge_template(
    center: "ConfigCenter",
    template_dir: str,
    template_name: str,
    version_path: str,
    exit_after_merge: bool,
) -> None:
    tpl_path = find_template(template_dir, template_name)
    if tpl_path is None:
        return
    try:
        tpl_raw = load_file(tpl_path)
    except Exception as exc:
        logger.debug("加载模板失败: %s", exc)
        return
    old_ver = center._dig(center._raw, version_path)
    new_ver = center._dig(tpl_raw, version_path)
    if old_ver is not _MISSING and new_ver is not _MISSING and old_ver == new_ver:
        return
    if center._path is None:
        return
    center.backup()
    merge_dicts(center._raw, tpl_raw)
    write_toml(center._path, center._raw)
    logger.debug("已合并模板新增字段到 %s", center._path)
    if exit_after_merge:
        raise SystemExit(0)


async def watch_config(center: "ConfigCenter", debounce: float = 0.5) -> None:
    if center._observer is not None:
        return
    if center._path is None:
        raise ConfigError("配置路径未设置，无法启动监控")
    center._debounce_delay = debounce
    center._loop = asyncio.get_running_loop()
    config_path = str(center._path)
    try:
        from watchdog.events import FileModifiedEvent, FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        raise ConfigError("watchdog 未安装: pip install watchdog") from None

    class _Handler(FileSystemEventHandler):
        def on_modified(handler_self, event: Any) -> None:
            if not isinstance(event, FileModifiedEvent):
                return
            if os.path.abspath(event.src_path) != os.path.abspath(config_path):
                return
            if center._loop:
                asyncio.run_coroutine_threadsafe(
                    debounced_reload(center), center._loop
                )

    center._observer = Observer()
    center._observer.schedule(_Handler(), str(center._path.parent), recursive=False)
    center._observer.start()
    logger.debug("已启动配置监控: %s", center._path)


async def stop_watch_config(center: "ConfigCenter") -> None:
    if center._observer is None:
        return
    center._observer.stop()
    center._observer.join(timeout=2)
    center._observer = None
    logger.debug("配置监控已停止")


async def debounced_reload(center: "ConfigCenter") -> None:
    import time

    trigger = time.time()
    center._last_reload_trigger = trigger
    await asyncio.sleep(center._debounce_delay)
    if center._last_reload_trigger > trigger:
        return
    if center._is_reloading:
        return
    center._is_reloading = True
    try:
        ok = await center.reload()
        if not ok:
            logger.error("配置重载失败")
    finally:
        center._is_reloading = False
