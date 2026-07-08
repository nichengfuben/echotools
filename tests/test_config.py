from __future__ import annotations

from dataclasses import dataclass

import pytest

from echotools.config import ConfigBase, ConfigCenter
from echotools.config.merge import merge_dicts
from echotools.errors import ConfigError


@dataclass
class ServerCfg(ConfigBase):
    port: int = 8080
    host: str = "127.0.0.1"


def test_dot_path_get() -> None:
    """点路径访问配置。"""
    cc = ConfigCenter()
    cc.load(data={"server": {"port": 8080}})
    assert cc.get("server.port") == 8080
    assert cc.get("server.missing", "x") == "x"


def test_set_and_get() -> None:
    """设置后读取。"""
    cc = ConfigCenter()
    cc.load(data={})
    cc.set("a.b.c", 1)
    assert cc.get("a.b.c") == 1


def test_raw_is_deep_copy() -> None:
    cc = ConfigCenter()
    cc.load(data={"x": 1})
    raw = cc.raw
    raw["x"] = 99
    assert cc.get("x") == 1


def test_bind_schema() -> None:
    cc = ConfigCenter()
    cc.load(data={"server": {"port": 9000, "host": "0.0.0.0"}})
    cfg = cc.bind(ServerCfg, "server")
    assert cfg.port == 9000
    assert cfg.host == "0.0.0.0"


def test_bind_invalid_section_raises() -> None:
    cc = ConfigCenter()
    cc.load(data={"server": "not-a-dict"})
    with pytest.raises(ConfigError):
        cc.bind(ServerCfg, "server")


def test_merge_dicts_via_center() -> None:
    target = {"a": 1}
    merge_dicts(target, {"b": 2})
    assert target == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_reload_callback(tmp_path) -> None:
    """变更回调触发。"""
    f = tmp_path / "c.json"
    f.write_text('{"x": 1}', encoding="utf-8")
    cc = ConfigCenter()
    cc.load(str(f))
    seen = []
    cc.on_change("x", lambda o, n: seen.append((o, n)))
    f.write_text('{"x": 2}', encoding="utf-8")
    ok = await cc.reload()
    assert ok
    assert seen == [(1, 2)]


@pytest.mark.asyncio
async def test_reload_missing_file_returns_false(tmp_path) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"x": 1}', encoding="utf-8")
    cc = ConfigCenter()
    cc.load(str(f))
    f.unlink()
    assert await cc.reload() is False
