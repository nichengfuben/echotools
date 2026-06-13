from __future__ import annotations

"""配置中心：通用点路径访问 + 类型化绑定 + 热重载 + 变更回调。

完全项目无关：不预设任何配置结构，由用户提供 schema 或直接点路径访问。
"""

import asyncio
import copy
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
)

from echotools.config.base import ConfigBase
from echotools.config.loader import find_config, find_template, load_file, write_toml
from echotools.config.merge import merge_dicts
from echotools.errors.common import ConfigError
from echotools.logger.manager import get_logger

__all__ = ["ConfigCenter"]

logger = get_logger(__name__)

C = TypeVar("C", bound=ConfigBase)

_MISSING = object()


class ConfigCenter:
    """通用配置中心。

    特性：
    - 点路径访问：cfg.get("server.port")
    - 类型化绑定：cfg.bind(MyConfig)
    - 热重载与变更回调
    - 完全不依赖具体配置结构
    """

    def __init__(self) -> None:
        """初始化配置中心。"""
        self._raw: Dict[str, Any] = {}
        self._path: Optional[Path] = None
        self._callbacks: Dict[str, List[Callable[[Any, Any], Any]]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._bound: Optional[ConfigBase] = None
        self._observer: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._debounce_delay: float = 0.5
        self._last_reload_trigger: float = 0.0
        self._is_reloading: bool = False

    def _get_lock(self) -> asyncio.Lock:
        """延迟初始化锁。"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def load(
        self,
        path: Optional[str] = None,
        *,
        filename: str = "config.toml",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """加载配置。

        Args:
            path: 配置文件路径。
            filename: 自动查找时的文件名。
            data: 直接提供字典（最高优先，跳过文件）。

        Returns:
            原始配置字典。

        Raises:
            ConfigError: 无法定位或解析配置。
        """
        if data is not None:
            self._raw = copy.deepcopy(data)
            return dict(self._raw)
        if path:
            self._path = Path(path).resolve()
        else:
            self._path = find_config(filename)
        if self._path is None:
            raise ConfigError("未找到配置文件: {}".format(filename))
        self._raw = load_file(self._path)
        logger.info("配置已加载: %s", self._path)
        return dict(self._raw)

    def get(self, path: str, default: Any = None) -> Any:
        """按点路径获取配置值。

        Args:
            path: 形如 "server.port" 的点路径。
            default: 缺省值。

        Returns:
            配置值或默认值。
        """
        node: Any = self._raw
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, path: str, value: Any) -> None:
        """按点路径设置配置值（内存中）。

        Args:
            path: 点路径。
            value: 新值。
        """
        parts = path.split(".")
        node = self._raw
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def bind(self, schema: Type[C], section: str = "") -> C:
        """将配置绑定到类型化 ConfigBase 子类。

        Args:
            schema: ConfigBase 子类。
            section: 子段点路径，空表示根。

        Returns:
            类型化配置实例。
        """
        data = self.get(section, {}) if section else self._raw
        if not isinstance(data, dict):
            raise ConfigError(
                "配置段 '{}' 不是字典".format(section or "<root>")
            )
        return schema.from_dict(data)

    @property
    def raw(self) -> Dict[str, Any]:
        """原始配置字典副本。"""
        return copy.deepcopy(self._raw)

    @property
    def path(self) -> Optional[Path]:
        """配置文件路径。"""
        return self._path

    def on_change(
        self, path: str, callback: Callable[[Any, Any], Any]
    ) -> None:
        """注册配置变更回调。

        Args:
            path: 监听的点路径。
            callback: 回调(old, new)，支持同步/异步。
        """
        self._callbacks.setdefault(path, []).append(callback)

    async def reload(self) -> bool:
        """热重载配置文件并触发变更回调。

        Returns:
            是否成功。
        """
        if self._path is None or not self._path.exists():
            return False
        async with self._get_lock():
            old = copy.deepcopy(self._raw)
            try:
                new = load_file(self._path)
            except Exception as exc:
                logger.error("配置重载失败: %s", exc, exc_info=True)
                return False
            self._raw = new
            await self._notify(old, new)
            logger.info("配置已重载: %s", self._path)
            return True

    async def _notify(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> None:
        """触发变更回调。"""
        for path, callbacks in self._callbacks.items():
            old_val = self._dig(old, path)
            new_val = self._dig(new, path)
            if old_val != new_val:
                logger.info("配置变更: %s", path)
                for cb in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(old_val, new_val)
                        else:
                            cb(old_val, new_val)
                    except Exception as exc:
                        logger.error(
                            "配置回调异常 [%s]: %s",
                            path,
                            exc,
                            exc_info=True,
                        )

    @staticmethod
    def _dig(data: Dict[str, Any], path: str) -> Any:
        """从字典按点路径取值。"""
        node: Any = data
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return _MISSING
        return node

    # ------------------------------------------------------------------
    # 模板初始化
    # ------------------------------------------------------------------

    def init_from_template(
        self,
        *,
        filename: str = "config.toml",
        template_dir: str = "template",
        template_name: str = "template_config.toml",
        version_path: str = "server.version",
        exit_after_create: bool = True,
        exit_after_merge: bool = True,
    ) -> Dict[str, Any]:
        """从模板初始化配置：不存在则创建，版本不同则合并新字段。

        Args:
            filename: 配置文件名。
            template_dir: 模板目录。
            template_name: 模板文件名。
            version_path: 版本号点路径，用于判断是否需要合并。
            exit_after_create: 新建配置后是否 SystemExit。
            exit_after_merge: 合并后是否 SystemExit。

        Returns:
            原始配置字典。
        """
        self._path = find_config(filename)

        if self._path is None:
            tpl = find_template(template_dir, template_name)
            if tpl is None:
                raise ConfigError(
                    "未找到配置或模板: {}/{}".format(template_dir, template_name)
                )
            target = Path.cwd() / filename
            shutil.copy2(str(tpl), str(target))
            self._path = target
            logger.info("从模板创建配置: %s", target)
            if exit_after_create:
                raise SystemExit(0)

        self._raw = load_file(self._path)
        self._try_merge_template(
            template_dir, template_name, version_path, exit_after_merge
        )
        logger.info("配置已加载: %s", self._path)
        return dict(self._raw)

    def _try_merge_template(
        self,
        template_dir: str,
        template_name: str,
        version_path: str,
        exit_after_merge: bool,
    ) -> None:
        """比较版本号，合并模板新增字段。"""
        tpl_path = find_template(template_dir, template_name)
        if tpl_path is None:
            return

        try:
            tpl_raw = load_file(tpl_path)
        except Exception as exc:
            logger.debug("加载模板失败: %s", exc)
            return

        old_ver = self._dig(self._raw, version_path)
        new_ver = self._dig(tpl_raw, version_path)

        if old_ver is not _MISSING and new_ver is not _MISSING and old_ver == new_ver:
            return

        if self._path is None:
            return

        self.backup()
        merge_dicts(self._raw, tpl_raw)
        write_toml(self._path, self._raw)
        logger.info("已合并模板新增字段到 %s", self._path)
        if exit_after_merge:
            raise SystemExit(0)

    # ------------------------------------------------------------------
    # 写入 & 备份
    # ------------------------------------------------------------------

    def write(self, data: Optional[Dict[str, Any]] = None) -> None:
        """将配置写回文件（tomlkit 保留注释）。

        Args:
            data: 要写入的字典，None 则写入当前 _raw。
        """
        if self._path is None:
            raise ConfigError("配置路径未设置")
        write_toml(self._path, data if data is not None else self._raw)
        if data is not None:
            self._raw = copy.deepcopy(data)

    def backup(self, backup_dir: Optional[str] = None) -> Optional[Path]:
        """创建配置文件的带时间戳备份。

        Args:
            backup_dir: 备份目录，默认 <config_dir>/template/old。

        Returns:
            备份文件路径，无配置路径时返回 None。
        """
        if self._path is None or not self._path.exists():
            return None
        if backup_dir is None:
            bdir = self._path.parent / "template" / "old"
        else:
            bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = bdir / "{}.bak.{}".format(self._path.name, ts)
        shutil.copy2(str(self._path), str(backup_path))
        logger.info("已备份: %s", backup_path)
        return backup_path

    # ------------------------------------------------------------------
    # __getattr__ 代理
    # ------------------------------------------------------------------

    def bind_proxy(self, schema: Type[C], section: str = "") -> C:
        """绑定 schema 并启用 __getattr__ 代理。

        调用后，cfg.server 等价于 cfg._bound.server。
        """
        bound = self.bind(schema, section)
        self._bound = bound
        return bound

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(
                "'{}' has no attribute '{}'".format(type(self).__name__, name)
            )
        if self._bound is None:
            raise AttributeError(
                "配置未绑定 schema，请先调用 bind_proxy()"
            )
        return getattr(self._bound, name)

    # ------------------------------------------------------------------
    # Watchdog 文件监控
    # ------------------------------------------------------------------

    async def watch(self, debounce: float = 0.5) -> None:
        """启动 watchdog 文件监控，文件变更时自动重载。

        Args:
            debounce: 防抖延迟（秒）。
        """
        if self._observer is not None:
            return
        if self._path is None:
            raise ConfigError("配置路径未设置，无法启动监控")

        self._debounce_delay = debounce
        self._loop = asyncio.get_running_loop()
        config_path = str(self._path)
        mgr = self

        try:
            from watchdog.events import FileModifiedEvent, FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            raise ConfigError("watchdog 未安装: pip install watchdog")

        class _Handler(FileSystemEventHandler):
            def on_modified(handler_self, event: Any) -> None:
                if not isinstance(event, FileModifiedEvent):
                    return
                if os.path.abspath(event.src_path) != os.path.abspath(config_path):
                    return
                if mgr._loop:
                    asyncio.run_coroutine_threadsafe(
                        mgr._debounced_reload(), mgr._loop
                    )

        self._observer = Observer()
        self._observer.schedule(_Handler(), str(self._path.parent), recursive=False)
        self._observer.start()
        logger.info("已启动配置监控: %s", self._path)

    async def stop_watch(self) -> None:
        """停止文件监控。"""
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2)
        self._observer = None
        logger.info("配置监控已停止")

    async def _debounced_reload(self) -> None:
        """防抖重载。"""
        import time

        trigger = time.time()
        self._last_reload_trigger = trigger
        await asyncio.sleep(self._debounce_delay)
        if self._last_reload_trigger > trigger:
            return
        if self._is_reloading:
            return
        self._is_reloading = True
        try:
            ok = await self.reload()
            if not ok:
                logger.error("配置重载失败")
        finally:
            self._is_reloading = False

    def __repr__(self) -> str:
        watching = self._observer is not None
        return "<ConfigCenter path={} watching={}>".format(self._path, watching)
