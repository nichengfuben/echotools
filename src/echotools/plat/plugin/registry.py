from __future__ import annotations

"""插件注册表：发现、注册、启停、热重载。"""

import asyncio
from typing import Any, Dict, List, Optional, Type

from echotools.base.logger.manager import get_logger
from echotools.plat.plugin.base import Plugin
from echotools.plat.plugin.discovery import discover_plugins
from echotools.plat.plugin.registry_ops import (
    init_discovered_plugin,
    purge_package_modules,
    reload_plugin,
    shutdown_plugin,
)

__all__ = ["PluginRegistry"]

logger = get_logger(__name__)


class PluginRegistry:
    """通用插件注册表。

    支持自动发现、黑白名单过滤、并发启动、热重载、统一关闭。
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, Any] = {}
        self._shutdown_method: str = "shutdown"

    async def discover_and_register(
        self,
        root_package: str,
        context: Any = None,
        *,
        whitelist: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
        base_class: Optional[Type] = None,
        required_methods: Optional[tuple] = None,
        init_method: str = "startup",
        shutdown_method: str = "shutdown",
    ) -> None:
        """发现并注册插件。"""
        self._shutdown_method = shutdown_method
        classes = discover_plugins(
            root_package,
            base_class=base_class,
            required_methods=required_methods,
        )
        if not classes:
            logger.warning("未发现任何插件: %s", root_package)
            return
        wl = set(whitelist) if whitelist else None
        bl = set(blacklist) if blacklist else set()
        logger.debug("发现 %d 个插件，开始注册", len(classes))

        await asyncio.gather(
            *[
                init_discovered_plugin(
                    self, c, context, wl, bl, init_method, shutdown_method
                )
                for c in classes
            ],
            return_exceptions=True,
        )
        logger.debug("注册完成: %s", list(self._plugins.keys()))

    def register(self, plugin: Plugin) -> None:
        """手动注册已实例化插件。"""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    @property
    def plugins(self) -> Dict[str, Plugin]:
        return dict(self._plugins)

    async def reload(
        self,
        name: str,
        root_package: str,
        context: Any = None,
        *,
        base_class: Optional[Type] = None,
        required_methods: Optional[tuple] = None,
        init_method: str = "startup",
        shutdown_method: Optional[str] = None,
    ) -> bool:
        """热重载指定插件；shutdown_method 默认沿用 discover_and_register 时的设定。"""
        sm = shutdown_method or self._shutdown_method
        old = self._plugins.get(name)
        if old is not None:
            await shutdown_plugin(old, sm, name)
        purge_package_modules(root_package)
        try:
            classes = discover_plugins(
                root_package,
                base_class=base_class,
                required_methods=required_methods,
            )
            return await reload_plugin(
                self, name, root_package, context, classes, init_method
            )
        except Exception as exc:
            logger.error("插件 [%s] 热重载失败: %s", name, exc)
            self._plugins.pop(name, None)
            return False

    async def close(self) -> None:
        """并发关闭全部插件。"""
        sm = self._shutdown_method

        async def _close_one(name: str, plugin: Any) -> None:
            try:
                shutdown_fn = getattr(plugin, sm, None)
                if shutdown_fn:
                    await asyncio.wait_for(shutdown_fn(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("关闭插件 [%s] 超时", name)
            except Exception as exc:
                logger.warning("关闭插件 [%s] 失败: %s", name, exc)

        await asyncio.gather(
            *[_close_one(n, p) for n, p in self._plugins.items()],
            return_exceptions=True,
        )
        self._plugins.clear()

    def get_by_capability(self, capability: str) -> Optional[Plugin]:
        """获取第一个支持指定能力的插件。"""
        for plugin in self._plugins.values():
            caps = getattr(plugin, "capabilities", {})
            if caps.get(capability, False):
                return plugin
        return None

    async def collect_from_all(
        self,
        method_name: str,
        *,
        filter_fn: Any = None,
    ) -> List[Any]:
        """调用所有插件的指定异步方法，聚合结果。"""
        results: List[Any] = []
        for name, plugin in self._plugins.items():
            method = getattr(plugin, method_name, None)
            if method is None:
                continue
            try:
                items = await method()
                if filter_fn is not None:
                    items = [i for i in items if filter_fn(i)]
                results.extend(items)
            except Exception as exc:
                logger.warning("[%s] %s 失败: %s", name, method_name, exc)
        return results

    async def all_items(
        self,
        items_attr: str = "supported_models",
        *,
        extra_attrs: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """收集所有插件的项目信息（去重）。"""

        out: List[Dict[str, Any]] = []
        seen: set = set()
        extra_attrs = extra_attrs or []

        for plugin in self._plugins.values():
            items = getattr(plugin, items_attr, []) or []
            caps = getattr(plugin, "capabilities", {})
            for item in items:
                if item in seen:
                    continue
                seen.add(item)
                entry: Dict[str, Any] = {
                    "id": item,
                    "owned_by": getattr(plugin, "name", ""),
                    "capabilities": dict(caps),
                }
                for attr in extra_attrs:
                    val = getattr(plugin, attr, None)
                    if val is not None:
                        entry[attr] = val
                out.append(entry)
        return out
