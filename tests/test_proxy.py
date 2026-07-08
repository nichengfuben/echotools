from __future__ import annotations

import pytest

from echotools.proxy.manager import ProxyManager


def test_proxy_url_matching_no_config() -> None:
    pm = ProxyManager()
    assert pm.should_proxy_url("https://api.example.com/v1") is False


def test_proxy_localhost_skipped() -> None:
    pm = ProxyManager()
    assert pm.should_proxy_url("http://localhost:8080/health") is False


def test_proxy_ip_skipped_when_active(monkeypatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
    pm = ProxyManager()
    pm.activate()
    assert pm.is_active()
    assert pm.should_proxy_url("http://192.168.1.1/api") is False


def test_proxy_domain_matches_pattern() -> None:
    pm = ProxyManager()
    pm.configure(
        proxy_server="http://127.0.0.1:7890",
        enabled=True,
        url_patterns=[r"api\.example\.com"],
    )
    pm.activate()
    assert pm.should_proxy_url("https://api.example.com/v1") is True
    assert pm.should_proxy_url("https://other.com/v1") is False


def test_proxy_deactivate_clears_state() -> None:
    pm = ProxyManager()
    pm.configure(proxy_server="http://127.0.0.1:7890", enabled=True)
    pm.activate()
    pm.deactivate()
    assert not pm.is_active()
    assert pm.get_proxy_dict() == {}


@pytest.mark.http
@pytest.mark.asyncio
async def test_make_aiohttp_connector_without_socks() -> None:
    pytest.importorskip("aiohttp")
    pm = ProxyManager()
    pm.configure(proxy_server="http://127.0.0.1:7890", enabled=True)
    pm.activate()
    connector = pm.make_aiohttp_connector()
    assert connector is not None
    await connector.close()
