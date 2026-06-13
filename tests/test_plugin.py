from __future__ import annotations

import pytest

from echotools.plugin import Plugin, PluginRegistry


class DummyPlugin(Plugin):
    started = False

    @property
    def name(self) -> str:
        return "dummy"

    async def startup(self, context=None) -> None:
        DummyPlugin.started = True

    async def shutdown(self) -> None:
        DummyPlugin.started = False


@pytest.mark.asyncio
async def test_manual_register_and_close() -> None:
    """手动注册与关闭。"""
    reg = PluginRegistry()
    p = DummyPlugin()
    await p.startup()
    reg.register(p)
    assert reg.get("dummy") is p
    await reg.close()
    assert reg.plugins == {}
