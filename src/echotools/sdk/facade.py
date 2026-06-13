from __future__ import annotations

"""EchoTools SDK 门面：一站式装配所有能力，支持调用链。"""

from pathlib import Path
from typing import Any, Optional

from echotools.cache.memory_cache import MemoryCache
from echotools.config.center import ConfigCenter
from echotools.dispatch.dispatcher import TaskDispatcher
from echotools.dispatch.selector import AdaptiveSelector
from echotools.events.bus import EventBus
from echotools.lifecycle.manager import LifecycleManager
from echotools.logger.manager import LoggerManager, get_logger
from echotools.plugin.registry import PluginRegistry
from echotools.proxy.manager import ProxyManager
from echotools.runtime.collector import RuntimeCollector
from echotools.scheduler.scheduler import TaskScheduler
from echotools.tracing.tracer import Tracer

__all__ = ["EchoTools"]

logger = get_logger(__name__)


class EchoTools:
    """EchoTools SDK 统一门面。

    懒加载装配配置、日志、事件、调度、插件、协议、调用链等全部能力，
    提供单一入口，支持链式访问。
    """

    def __init__(
        self,
        *,
        service_name: str = "echotools",
        persist_dir: str = "data/echotools",
    ) -> None:
        """初始化 SDK。

        Args:
            service_name: 服务名（用于日志/运行时摘要）。
            persist_dir: 持久化根目录。
        """
        self._service_name = service_name
        self._persist_dir = Path(persist_dir)
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

    @property
    def config(self) -> ConfigCenter:
        """配置中心。"""
        if self._config is None:
            self._config = ConfigCenter()
        return self._config

    @property
    def logger(self) -> LoggerManager:
        """日志管理器。"""
        if self._logger_manager is None:
            self._logger_manager = LoggerManager()
        return self._logger_manager

    @property
    def events(self) -> EventBus:
        """事件总线。"""
        if self._events is None:
            self._events = EventBus()
        return self._events

    @property
    def cache(self) -> MemoryCache:
        """内存缓存。"""
        if self._cache is None:
            self._cache = MemoryCache()
        return self._cache

    @property
    def scheduler(self) -> TaskScheduler:
        """任务调度器。"""
        if self._scheduler is None:
            self._scheduler = TaskScheduler()
        return self._scheduler

    @property
    def lifecycle(self) -> LifecycleManager:
        """生命周期管理器。"""
        if self._lifecycle is None:
            self._lifecycle = LifecycleManager()
        return self._lifecycle

    @property
    def proxy(self) -> ProxyManager:
        """代理管理器。"""
        if self._proxy is None:
            self._proxy = ProxyManager()
        return self._proxy

    @property
    def plugins(self) -> PluginRegistry:
        """插件注册表。"""
        if self._plugins is None:
            self._plugins = PluginRegistry()
        return self._plugins

    @property
    def selector(self) -> AdaptiveSelector:
        """自适应选择器。"""
        if self._selector is None:
            self._selector = AdaptiveSelector(
                persist_dir=str(self._persist_dir / "dispatch")
            )
        return self._selector

    @property
    def dispatcher(self) -> TaskDispatcher:
        """任务调度分发器。"""
        if self._dispatcher is None:
            self._dispatcher = TaskDispatcher(selector=self.selector)
        return self._dispatcher

    @property
    def tracer(self) -> Tracer:
        """调用链追踪器。"""
        if self._tracer is None:
            self._tracer = Tracer()
        return self._tracer

    @property
    def runtime(self) -> RuntimeCollector:
        """运行时收集器。"""
        if self._runtime is None:
            self._runtime = RuntimeCollector(self._service_name)
        return self._runtime

    async def shutdown(self) -> None:
        """优雅关闭：插件、调度、生命周期。"""
        if self._plugins is not None:
            await self._plugins.close()
        if self._scheduler is not None:
            await self._scheduler.cancel_all()
        if self._lifecycle is not None:
            await self._lifecycle.shutdown()
        logger.info("EchoTools 已关闭")
