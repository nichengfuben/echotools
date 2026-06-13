from __future__ import annotations

"""插件自动发现：递归扫描包，识别 Plugin 子类。"""

import importlib
import pkgutil
from typing import Any, List, Set

from echotools.logger.manager import get_logger
from echotools.plugin.base import Plugin

__all__ = ["discover_plugins"]

logger = get_logger(__name__)


def _is_plugin_class(attr: Any, root_package: str) -> bool:
    """判断对象是否为合法插件类。"""
    if not isinstance(attr, type):
        return False
    if attr is Plugin:
        return False
    module_name = getattr(attr, "__module__", "")
    if not module_name.startswith(root_package):
        return False
    try:
        if not issubclass(attr, Plugin):
            return False
    except TypeError:
        return False
    if getattr(attr, "__abstractmethods__", None):
        return False
    return True


def _collect_from_module(
    module: Any,
    root_package: str,
    discovered: List[type],
    seen: Set[str],
) -> None:
    """从模块收集插件类。"""
    for attr_name in dir(module):
        try:
            attr = getattr(module, attr_name)
        except Exception as exc:
            logger.debug("获取属性 %s 失败: %s", attr_name, exc)
            continue
        if not _is_plugin_class(attr, root_package):
            continue
        key = "{}.{}".format(
            getattr(attr, "__module__", ""),
            getattr(attr, "__qualname__", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        discovered.append(attr)


def _scan_tree(
    package: Any,
    root_package: str,
    discovered: List[type],
    seen_modules: Set[str],
    seen_classes: Set[str],
    skip_names: Set[str],
) -> None:
    """递归扫描包树。"""
    pkg_path = getattr(package, "__path__", None)
    if pkg_path is None:
        return
    for module_info in pkgutil.iter_modules(
        pkg_path, package.__name__ + "."
    ):
        module_name = module_info.name
        if module_name in seen_modules:
            continue
        base_name = module_name.rsplit(".", 1)[-1]
        if base_name in skip_names:
            continue
        seen_modules.add(module_name)
        try:
            mod = importlib.import_module(module_name)
        except Exception as exc:
            logger.warning("加载 %s 失败: %s", module_name, exc)
            continue
        _collect_from_module(mod, root_package, discovered, seen_classes)
        if module_info.ispkg:
            _scan_tree(
                mod,
                root_package,
                discovered,
                seen_modules,
                seen_classes,
                skip_names,
            )


def discover_plugins(
    root_package: str,
    skip_names: Set[str] = None,  # type: ignore[assignment]
) -> List[type]:
    """递归发现指定包下的所有插件类。

    Args:
        root_package: 根包名，如 'myapp.plugins'。
        skip_names: 跳过的模块名集合（如测试模块）。

    Returns:
        插件类列表。
    """
    if skip_names is None:
        skip_names = {"test", "tests", "client"}
    discovered: List[type] = []
    seen_modules: Set[str] = set()
    seen_classes: Set[str] = set()
    try:
        root_mod = importlib.import_module(root_package)
    except Exception as exc:
        logger.warning("导入 %s 失败: %s", root_package, exc)
        return discovered
    _collect_from_module(
        root_mod, root_package, discovered, seen_classes
    )
    _scan_tree(
        root_mod,
        root_package,
        discovered,
        seen_modules,
        seen_classes,
        skip_names,
    )
    return discovered
