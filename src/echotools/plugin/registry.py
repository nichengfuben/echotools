from __future__ import annotations

"""插件注册表：发现、注册、启停、热重载。"""

import asyncio
import sys
from typing import Any, Dict, List, Optional

from echotools.logger.manager import get_logger
from echotools.plugin.base import Plugin
from echotools.plugin.discovery import discover_plugins

__all__ = ["PluginRegistry"]

logger = get_logger(__name__)


class PluginRegistry:
    """通用插件注册表。

    支持自动发现、黑白名单过滤、并发启动、热重载、统一关闭。
    """

    def __init__(self) -> None:
        """初始化注册表。"""
        self._plugins: Dict[str, Plugin] = {}

    async def discover_and_register(
        self,
        root_package: str,
        context: Any = None,
        *,
        whitelist: Optional[List[str]] = None,
        blacklist: Optional[List[str]] = None,
    ) -> None:
        """发现并注册插件。

        Args:
            root_package: 插件根包名。
            context: 共享上下文，传给 startup。
            whitelist: 白名单（仅注册名单内）。
            blacklist: 黑名单（排除名单内）。
        """
        classes = discover_plugins(root_package)
        if not classes:
            logger.warning("未发现任何插件: %s", root_package)
            return
        wl = set(whitelist) if whitelist else None
        bl = set(blacklist) if blacklist else set()
        logger.info("发现 %d 个插件，开始注册", len(classes))

        async def _init_one(cls: type) -> None:
            try:
                plugin = cls()
            except Exception as exc:
                logger.error("实例化插件 %s 失败: %s", cls.__name__, exc)
                return
            name = plugin.name
            if wl is not None and name not in wl:
                logger.info("插件 [%s] 不在白名单，跳过", name)
                return
            if name in bl:
                logger.info("插件 [%s] 在黑名单，跳过", name)
                return
            try:
                await plugin.startup(context)
                self._plugins[name] = plugin
                logger.info("插件 [%s] 已注册", name)
            except Exception as exc:
                logger.error("插件 [%s] 启动失败: %s", name, exc)
                try:
                    await plugin.shutdown()
                except Exception as e:
                    logger.warning("插件 [%s] 回滚关闭异常: %s", name, e)

        await asyncio.gather(
            *[_init_one(c) for c in classes], return_exceptions=True
        )
        logger.info("注册完成: %s", list(self._plugins.keys()))

    def register(self, plugin: Plugin) -> None:
        """手动注册已实例化插件。"""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Optional[Plugin]:
        """获取指定插件。"""
        return self._plugins.get(name)

    @property
    def plugins(self) -> Dict[str, Plugin]:
        """全部插件字典。"""
        return dict(self._plugins)

    async def reload(
        self,
        name: str,
        root_package: str,
        context: Any = None,
    ) -> bool:
        """热重载指定插件。

        Args:
            name: 插件名。
            root_package: 该插件所在的子包名。
            context: 共享上下文。

        Returns:
            是否成功。
        """
        old = self._plugins.get(name)
        if old is not None:
            try:
                await old.shutdown()
            except Exception as exc:
                logger.warning("关闭旧插件 [%s] 失败: %s", name, exc)
        prefix = root_package
        to_remove = sorted(
            [
                k
                for k in sys.modules
                if k == prefix or k.startswith(prefix + ".")
            ],
            key=lambda x: -len(x),
        )
        for mod_key in to_remove:
            del sys.modules[mod_key]
        try:
            classes = discover_plugins(prefix)
            target = None
            for cls in classes:
                try:
                    inst = cls()
                except Exception:
                    continue
                if inst.name == name:
                    target = inst
                    break
            if target is None:
                logger.error("重载 [%s] 未找到匹配插件", name)
                return False
            await target.startup(context)
            self._plugins[name] = target
            logger.info("插件 [%s] 热重载成功", name)
            return True
        except Exception as exc:
            logger.error("插件 [%s] 热重载失败: %s", name, exc)
            self._plugins.pop(name, None)
            return False

    async def close(self) -> None:
        """并发关闭全部插件。"""

        async def _close_one(name: str, plugin: Plugin) -> None:
            try:
                await asyncio.wait_for(plugin.shutdown(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("关闭插件 [%s] 超时", name)
            except Exception as exc:
                logger.warning("关闭插件 [%s] 失败: %s", name, exc)

        await asyncio.gather(
            *[_close_one(n, p) for n, p in self._plugins.items()],
            return_exceptions=True,
        )
        self._plugins.clear()

    # ------------------------------------------------------------------
    # 能力查询 & 聚合
    # ------------------------------------------------------------------

    def get_by_capability(self, capability: str) -> Optional[Plugin]:
        """获取第一个支持指定能力的插件。

        Args:
            capability: 能力名称。

        Returns:
            插件实例或 None。
        """
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
        """调用所有插件的指定异步方法，聚合结果。

        Args:
            method_name: 插件上的异步方法名（如 'candidates'）。
            filter_fn: 可选的过滤函数，接收单个结果项，返回 bool。

        Returns:
            所有插件返回结果的聚合列表。
        """
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
        """收集所有插件的项目信息（去重）。

        Args:
            items_attr: 插件上的属性名（如 'supported_models'）。
            extra_attrs: 额外需要收集的属性（如 'capabilities', 'context_length'）。

        Returns:
            去重后的项目字典列表。
        """
        import time

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
