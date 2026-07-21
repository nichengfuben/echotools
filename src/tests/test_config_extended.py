from __future__ import annotations

import pytest

from echotools.base.config import ConfigCenter


@pytest.mark.asyncio
async def test_config_write_toml(tmp_path) -> None:
    pytest.importorskip("tomlkit")
    f = tmp_path / "cfg.toml"
    f.write_text('a = 1\n', encoding="utf-8")
    cc = ConfigCenter()
    cc.load(str(f))
    cc.set("b", 2)
    cc.write()
    text = f.read_text(encoding="utf-8")
    assert "b" in text


def test_config_backup(tmp_path) -> None:
    f = tmp_path / "cfg.json"
    f.write_text('{"x": 1}', encoding="utf-8")
    cc = ConfigCenter()
    cc.load(str(f))
    backup = cc.backup(backup_dir=str(tmp_path / "bak"))
    assert backup is not None
    assert backup.exists()


@pytest.mark.asyncio
async def test_config_async_change_callback(tmp_path) -> None:
    f = tmp_path / "c.json"
    f.write_text('{"x": 1}', encoding="utf-8")
    cc = ConfigCenter()
    cc.load(str(f))
    seen = []

    async def on_change(old, new) -> None:
        seen.append((old, new))

    cc.on_change("x", on_change)
    f.write_text('{"x": 3}', encoding="utf-8")
    await cc.reload()
    assert seen == [(1, 3)]
