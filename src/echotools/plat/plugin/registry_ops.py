from __future__ import annotations

import sys
from typing import Any, List, Optional

from echotools.base.logger.manager import get_logger

logger = get_logger(__name__)


def purge_package_modules(prefix: str) -> None:
    to_remove = sorted(
        [k for k in sys.modules if k == prefix or k.startswith(prefix + ".")],
        key=lambda x: -len(x),
    )
    for mod_key in to_remove:
        del sys.modules[mod_key]


async def shutdown_plugin(plugin: Any, shutdown_method: str, name: str) -> None:
    try:
        old_shutdown = getattr(plugin, shutdown_method, None)
        if old_shutdown:
            await old_shutdown()
    except Exception as exc:
        logger.warning("关闭旧插件 [%s] 失败: %s", name, exc)


def find_plugin_instance(classes: List[type], name: str) -> Optional[Any]:
    for cls in classes:
        try:
            inst = cls()
        except Exception:
            continue
        if getattr(inst, "name", None) == name:
            return inst
    return None


async def reload_plugin(
    registry: Any,
    name: str,
    root_package: str,
    context: Any,
    classes: List[type],
    init_method: str,
) -> bool:
    target = find_plugin_instance(classes, name)
    if target is None:
        found = [
            "{}.{}".format(getattr(cls, "__module__", "?"), cls.__name__)
            for cls in classes
        ]
        logger.error(
            "重载 [%s] 未找到匹配插件 (发现 %d 个类: %s)",
            name, len(classes), found,
        )
        return False
    init_fn = getattr(target, init_method)
    await init_fn(context)
    registry._plugins[name] = target
    logger.debug("插件 [%s] 热重载成功", name)
    return True


async def init_discovered_plugin(
    registry: Any,
    cls: type,
    context: Any,
    wl: Optional[set],
    bl: set,
    init_method: str,
    shutdown_method: str,
) -> None:
    try:
        plugin = cls()
    except Exception as exc:
        logger.error("实例化插件 %s 失败: %s", cls.__name__, exc)
        return
    name = getattr(plugin, "name", cls.__name__)
    if wl is not None and name not in wl:
        logger.debug("插件 [%s] 不在白名单，跳过", name)
        return
    if name in bl:
        logger.debug("插件 [%s] 在黑名单，跳过", name)
        return
    try:
        init_fn = getattr(plugin, init_method)
        await init_fn(context)
        registry._plugins[name] = plugin
        logger.debug("插件 [%s] 已注册", name)
    except Exception as exc:
        logger.error("插件 [%s] 启动失败: %s", name, exc)
        try:
            shutdown_fn = getattr(plugin, shutdown_method, None)
            if shutdown_fn:
                await shutdown_fn()
        except Exception as e:
            logger.warning("插件 [%s] 回滚关闭异常: %s", name, e)
