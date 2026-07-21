from __future__ import annotations

"""插件自动发现：递归扫描包，识别指定基类的子类。"""

import importlib
import pkgutil
from typing import Any, List, Optional, Set, Type

from echotools.base.logger.manager import get_logger
from echotools.plat.plugin.base import Plugin

__all__ = ["discover_plugins"]

logger = get_logger(__name__)


def _is_plugin_class(
    attr: Any,
    root_package: str,
    base_class: Type,
    required_methods: Optional[tuple] = None,
) -> bool:
    """判断对象是否为合法插件类。"""
    if not isinstance(attr, type):
        return False
    if attr is base_class:
        return False
    module_name = getattr(attr, "__module__", "")
    if not module_name.startswith(root_package):
        return False
    # 检查基类继承
    try:
        is_sub = issubclass(attr, base_class)
    except TypeError:
        return False
    # 如果不是直接子类，检查鸭子类型（required_methods）
    if not is_sub:
        if required_methods is None:
            return False
        for method_name in required_methods:
            member = getattr(attr, method_name, None)
            if member is None or not callable(member):
                return False
        # 鸭子类型还要求有 name 属性
        name_member = getattr(attr, "name", None)
        if not isinstance(name_member, property):
            return False
    if getattr(attr, "__abstractmethods__", None):
        return False
    return True


def _collect_from_module(
    module: Any,
    root_package: str,
    discovered: List[type],
    seen: Set[str],
    base_class: Type,
    required_methods: Optional[tuple] = None,
) -> None:
    """从模块收集插件类。

    同时检查 dir() 和 __all__：使用 __getattr__ 延迟加载（PEP 562）
    的模块，dir() 不包含这些名称，但 __all__ 会声明它们。
    """
    names = set(dir(module))
    all_names = getattr(module, "__all__", None)
    if all_names:
        names.update(all_names)
    for attr_name in names:
        try:
            attr = getattr(module, attr_name)
        except Exception as exc:
            logger.debug("获取属性 %s 失败: %s", attr_name, exc)
            continue
        if not _is_plugin_class(attr, root_package, base_class, required_methods):
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
    base_class: Type,
    required_methods: Optional[tuple] = None,
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
        _collect_from_module(
            mod, root_package, discovered, seen_classes,
            base_class, required_methods,
        )
        if module_info.ispkg:
            _scan_tree(
                mod,
                root_package,
                discovered,
                seen_modules,
                seen_classes,
                skip_names,
                base_class,
                required_methods,
            )


def discover_plugins(
    root_package: str,
    skip_names: Set[str] = None,  # type: ignore[assignment]
    *,
    base_class: Optional[Type] = None,
    required_methods: Optional[tuple] = None,
) -> List[type]:
    """递归发现指定包下的所有插件类。

    Args:
        root_package: 根包名，如 'myapp.plugins'。
        skip_names: 跳过的模块名集合。
        base_class: 基类，默认 Plugin。传入自定义基类可发现其子类。
        required_methods: 鸭子类型所需方法名元组。非 base_class 子类
            但有这些方法且有 name property 的类也会被识别。

    Returns:
        插件类列表。
    """
    if skip_names is None:
        skip_names = {"test", "tests", "client"}
    if base_class is None:
        base_class = Plugin
    discovered: List[type] = []
    seen_modules: Set[str] = set()
    seen_classes: Set[str] = set()
    try:
        root_mod = importlib.import_module(root_package)
    except Exception as exc:
        logger.warning("导入 %s 失败: %s", root_package, exc)
        return discovered
    _collect_from_module(
        root_mod, root_package, discovered, seen_classes,
        base_class, required_methods,
    )
    _scan_tree(
        root_mod,
        root_package,
        discovered,
        seen_modules,
        seen_classes,
        skip_names,
        base_class,
        required_methods,
    )
    return discovered
