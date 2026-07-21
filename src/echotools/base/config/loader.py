from __future__ import annotations

"""配置文件加载器：支持 TOML / JSON，跨版本兼容。"""

import json
from pathlib import Path
from typing import Any, Dict

from echotools.base.errors.common import ConfigError

__all__ = ["load_file", "find_config", "find_template", "write_toml"]

try:
    import tomllib as _tomllib  # type: ignore[import]
except ImportError:
    try:
        import tomli as _tomllib  # type: ignore[import,no-redef]
    except ImportError:
        _tomllib = None  # type: ignore[assignment]


def load_file(path: Path) -> Dict[str, Any]:
    """加载配置文件，按扩展名选择解析器。

    Args:
        path: 配置文件路径。

    Returns:
        解析后的字典。

    Raises:
        ConfigError: 文件不存在或解析失败。
    """
    if not path.is_file():
        raise ConfigError("配置文件不存在: {}".format(path))
    suffix = path.suffix.lower()
    if suffix in (".toml",):
        if _tomllib is None:
            raise ConfigError("缺少 tomllib/tomli，无法解析 TOML")
        with open(str(path), "rb") as f:
            return _tomllib.load(f)
    if suffix in (".json",):
        with open(str(path), "r", encoding="utf-8") as f:
            return json.load(f)
    raise ConfigError("不支持的配置格式: {}".format(suffix))


def find_config(
    filename: str = "config.toml",
    env_var: str = "CONFIG_PATH",
    max_depth: int = 5,
) -> "Path | None":
    """向上查找配置文件。

    Args:
        filename: 配置文件名。
        env_var: 环境变量名（优先）。
        max_depth: 向上查找最大层数。

    Returns:
        找到的路径或 None。
    """
    import os

    env = os.environ.get(env_var)
    if env and Path(env).is_file():
        return Path(env).resolve()
    d = Path.cwd()
    for _ in range(max_depth):
        candidate = d / filename
        if candidate.is_file():
            return candidate.resolve()
        if d.parent == d:
            break
        d = d.parent
    return None


def find_template(
    template_dir: str = "template",
    template_name: str = "template_config.toml",
) -> "Path | None":
    """查找配置模板文件。

    在当前目录和脚本所在目录的 template_dir 子目录中查找。

    Args:
        template_dir: 模板目录名。
        template_name: 模板文件名。

    Returns:
        找到的路径或 None。
    """
    for base in [Path.cwd(), Path(__file__).parent.parent.parent.parent]:
        tpl = base / template_dir / template_name
        if tpl.is_file():
            return tpl.resolve()
    return None


def write_toml(path: Path, data: Dict[str, Any]) -> None:
    """用 tomlkit 将字典写入 TOML 文件（保留注释）。

    若 tomlkit 不可用则退化为 tomli_w 或手动写入。

    Args:
        path: 目标文件路径。
        data: 要写入的字典。

    Raises:
        ConfigError: 写入失败。
    """
    try:
        import tomlkit
    except ImportError:
        raise ConfigError("缺少 tomlkit，无法写入 TOML: pip install tomlkit")

    doc = tomlkit.document()
    _dict_to_toml(doc, data, tomlkit)
    with open(str(path), "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(doc))


def _dict_to_toml(doc: Any, data: Dict[str, Any], tomlkit: Any) -> None:
    """递归将字典写入 tomlkit document/table。"""
    for key, value in data.items():
        if isinstance(value, dict):
            if key not in doc or not isinstance(doc.get(key), (dict,)):
                try:
                    doc[key] = tomlkit.table()
                except Exception:
                    doc[key] = {}
            _dict_to_toml(doc[key], value, tomlkit)
        else:
            try:
                doc[key] = tomlkit.item(value)
            except (TypeError, ValueError):
                doc[key] = value
