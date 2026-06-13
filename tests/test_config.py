from __future__ import annotations

import pytest

from echotools.config import ConfigCenter


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
