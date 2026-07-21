from __future__ import annotations

"""EchoTools SDK 门面：一站式装配所有能力，支持调用链。"""

import asyncio
from pathlib import Path
from typing import FrozenSet, Optional, Set

from echotools.base.cache.memory_cache import MemoryCache
from echotools.base.config.center import ConfigCenter
from echotools.base.logger.manager import LoggerManager, get_logger
from echotools.exec.dispatch.dispatcher import TaskDispatcher
from echotools.exec.dispatch.selector import AdaptiveSelector
from echotools.exec.lifecycle.manager import LifecycleManager
from echotools.media.events.bus import EventBus
from echotools.media.tracing.tracer import Tracer
from echotools.plat.plugin.registry import PluginRegistry
from echotools.plat.proxy.manager import ProxyManager
from echotools.plat.runtime.collector import RuntimeCollector
from echotools.plat.scheduler.scheduler import TaskScheduler

__all__ = ["EchoTools"]

logger = get_logger(__name__)

_DEFAULT_PERSIST = Path.home() / ".echotools"
_ALL_MODULES = frozenset({
    "config",
    "logger",
    "events",
    "cache",
    "scheduler",
    "lifecycle",
    "proxy",
    "plugins",
    "selector",
    "dispatcher",
    "tracer",
    "runtime",
})


class EchoTools:
    """EchoTools SDK 统一门面。

    懒加载装配配置、日志、事件、调度、插件、协议、调用链等全部能力，
    提供单一入口，支持链式访问。
    """

    def __init__(
        self,
        *,
        service_name: str = "echotools",
        persist_dir: Optional[str] = None,
        enabled_modules: Optional[FrozenSet[str]] = None,
        cache_cleanup_interval: float = 0.0,
    ) -> None:
        """初始化 SDK。

        Args:
            service_name: 服务名（用于日志/运行时摘要）。
            persist_dir: 持久化根目录，默认 ~/.echotools。
            enabled_modules: 启用的子模块集合，None 表示全部启用。
            cache_cleanup_interval: 缓存过期清理间隔（秒），0 表示禁用。
        """
        self._service_name = service_name
        self._persist_dir = Path(persist_dir or _DEFAULT_PERSIST)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._enabled = enabled_modules or _ALL_MODULES
        self._cache_cleanup_interval = cache_cleanup_interval
        self._cache_cleanup_task: Optional[asyncio.Task[None]] = None
        self._config: Optional[ConfigCenter] = None
        self._logger_manager: Optional[LoggerManager] = None
        self._events: Optional[EventBus] = None
        self._cache: Optional[MemoryCache] = None
        self._scheduler: Optional[TaskScheduler] = None
        self._lifecycle: Optional[LifecycleManager] = None
        self._proxy: Optional[ProxyManager] = None
        self._plugins: Optional[PluginRegistry] = None
        self._selector: Optional[AdaptiveSelector] = None
        self._dispatcher: Optional[TaskDispatcher] = None
        self._tracer: Optional[Tracer] = None
        self._runtime: Optional[RuntimeCollector] = None
        self._started = False

    def _check_module(self, name: str) -> None:
        if name not in self._enabled:
            raise RuntimeError(f"Module {name!r} is disabled on this EchoTools instance")

    @property
    def config(self) -> ConfigCenter:
        """配置中心。"""
        self._check_module("config")
        if self._config is None:
            self._config = ConfigCenter()
        return self._config

    @property
    def logger(self) -> LoggerManager:
        """日志管理器。"""
        self._check_module("logger")
        if self._logger_manager is None:
            self._logger_manager = LoggerManager()
        return self._logger_manager

    @property
    def events(self) -> EventBus:
        """事件总线。"""
        self._check_module("events")
        if self._events is None:
            self._events = EventBus()
        return self._events

    @property
    def cache(self) -> MemoryCache:
        """内存缓存。"""
        self._check_module("cache")
        if self._cache is None:
            self._cache = MemoryCache()
        return self._cache

    @property
    def scheduler(self) -> TaskScheduler:
        """任务调度器。"""
        self._check_module("scheduler")
        if self._scheduler is None:
            self._scheduler = TaskScheduler()
        return self._scheduler

    @property
    def lifecycle(self) -> LifecycleManager:
        """生命周期管理器。"""
        self._check_module("lifecycle")
        if self._lifecycle is None:
            self._lifecycle = LifecycleManager()
        return self._lifecycle

    @property
    def proxy(self) -> ProxyManager:
        """代理管理器。"""
        self._check_module("proxy")
        if self._proxy is None:
            self._proxy = ProxyManager()
        return self._proxy

    @property
    def plugins(self) -> PluginRegistry:
        """插件注册表。"""
        self._check_module("plugins")
        if self._plugins is None:
            self._plugins = PluginRegistry()
        return self._plugins

    @property
    def selector(self) -> AdaptiveSelector:
        """自适应选择器。"""
        self._check_module("selector")
        if self._selector is None:
            self._selector = AdaptiveSelector(
                persist_dir=str(self._persist_dir / "dispatch")
            )
        return self._selector

    @property
    def dispatcher(self) -> TaskDispatcher:
        """任务调度分发器。"""
        self._check_module("dispatcher")
        if self._dispatcher is None:
            self._dispatcher = TaskDispatcher(selector=self.selector)
        return self._dispatcher

    @property
    def tracer(self) -> Tracer:
        """调用链追踪器。"""
        self._check_module("tracer")
        if self._tracer is None:
            self._tracer = Tracer()
        return self._tracer

    @property
    def runtime(self) -> RuntimeCollector:
        """运行时收集器。"""
        self._check_module("runtime")
        if self._runtime is None:
            self._runtime = RuntimeCollector(self._service_name)
        return self._runtime

    def _initialized_modules(self) -> Set[str]:
        mapping = {
            "config": self._config,
            "logger": self._logger_manager,
            "events": self._events,
            "cache": self._cache,
            "scheduler": self._scheduler,
            "lifecycle": self._lifecycle,
            "proxy": self._proxy,
            "plugins": self._plugins,
            "selector": self._selector,
            "dispatcher": self._dispatcher,
            "tracer": self._tracer,
            "runtime": self._runtime,
        }
        return {name for name, value in mapping.items() if value is not None}

    def __repr__(self) -> str:
        return (
            f"EchoTools(service={self._service_name!r}, "
            f"initialized={sorted(self._initialized_modules())})"
        )

    async def startup(self) -> None:
        """启动：生命周期钩子、可选缓存清理。"""
        if self._started:
            return
        if "lifecycle" in self._enabled:
            await self.lifecycle.startup()
        if (
            self._cache_cleanup_interval > 0
            and "cache" in self._enabled
        ):
            self._cache_cleanup_task = asyncio.create_task(
                self._cache_cleanup_loop()
            )
        self._started = True
        logger.debug("EchoTools started")

    async def _cache_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cache_cleanup_interval)
            if self._cache is not None:
                self._cache.cleanup()

    async def shutdown(self) -> None:
        """优雅关闭：刷盘、插件、调度、生命周期。"""
        if self._cache_cleanup_task is not None:
            self._cache_cleanup_task.cancel()
            try:
                await self._cache_cleanup_task
            except asyncio.CancelledError:
                pass
            self._cache_cleanup_task = None
        if "selector" in self._enabled and self._selector is not None:
            await self._selector.flush()
        if "plugins" in self._enabled and self._plugins is not None:
            await self._plugins.close()
        if "scheduler" in self._enabled and self._scheduler is not None:
            await self._scheduler.cancel_all()
        if "lifecycle" in self._enabled and self._lifecycle is not None:
            await self._lifecycle.shutdown()
        self._started = False
        logger.debug("EchoTools 已关闭")
