from __future__ import annotations

import pytest

from echotools import EchoTools
from echotools.base.errors.http import AuthError, RateLimitError, ServerError
from echotools.plat.plugin.base import Plugin


class _DummyPlugin(Plugin):
    @property
    def name(self) -> str:
        return "dummy"

    async def startup(self, context=None) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def test_http_errors_status_codes() -> None:
    assert AuthError("x").status_code == 401
    assert RateLimitError("x").status_code == 429
    assert ServerError("x", http_status=502).status_code == 502


def test_plugin_base_contract() -> None:
    p = _DummyPlugin()
    assert p.name == "dummy"
    assert p.capabilities == {}


@pytest.mark.asyncio
async def test_facade_all_modules_accessible(tmp_path) -> None:
    et = EchoTools(service_name="all", persist_dir=str(tmp_path))
    assert et.config is not None
    assert et.events is not None
    assert et.cache is not None
    assert et.scheduler is not None
    assert et.lifecycle is not None
    assert et.proxy is not None
    assert et.plugins is not None
    assert et.selector is not None
    assert et.dispatcher is not None
    assert et.tracer is not None
    assert et.runtime is not None
    await et.shutdown()
