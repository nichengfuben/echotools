from __future__ import annotations

from pathlib import Path

from echotools.dispatch.proxy_selector import ProxyRecord, ProxySelector


def test_proxy_record_success_rate() -> None:
    rec = ProxyRecord(n_success=3, n_fails=1)
    assert 0.0 < rec.success_rate < 1.0
    assert rec.mean_latency == 1000.0


def test_proxy_selector_record_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "proxy.json"
    sel = ProxySelector(path)
    sel.record(use_proxy=True, success=True, latency_ms=100.0)
    sel.record(use_proxy=False, success=False)

    reloaded = ProxySelector(path)
    assert reloaded._proxy.n_success == 1
    assert reloaded._direct.n_fails == 1


def test_proxy_selector_select_returns_bool(tmp_path: Path) -> None:
    sel = ProxySelector(tmp_path / "p.json")
    assert isinstance(sel.select(), bool)
