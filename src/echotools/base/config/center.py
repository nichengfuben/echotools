from __future__ import annotations

"""配置中心：通用点路径访问 + 类型化绑定 + 热重载 + 变更回调。

完全项目无关：不预设任何配置结构，由用户提供 schema 或直接点路径访问。
"""

import asyncio
import copy
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

from echotools.base.config.base import ConfigBase
from echotools.base.config.center_notify import notify_config_changes
from echotools.base.config.center_template import (
    debounced_reload,
    init_from_template,
    stop_watch_config,
    watch_config,
)
from echotools.base.config.loader import find_config, load_file, write_toml
from echotools.base.errors.common import ConfigError
from echotools.base.logger.manager import get_logger

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
        logger.debug("配置已加载: %s", self._path)
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
            logger.debug("配置已重载: %s", self._path)
            return True

    async def _notify(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> None:
        await notify_config_changes(self._callbacks, old, new, self._dig)

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

    def init_from_template(self, **kwargs: Any) -> Dict[str, Any]:
        return init_from_template(self, **kwargs)

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
        logger.debug("已备份: %s", backup_path)
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

    async def watch(self, debounce: float = 0.5) -> None:
        await watch_config(self, debounce)

    async def stop_watch(self) -> None:
        await stop_watch_config(self)

    async def _debounced_reload(self) -> None:
        await debounced_reload(self)

    def __repr__(self) -> str:
        watching = self._observer is not None
        return "<ConfigCenter path={} watching={}>".format(self._path, watching)
