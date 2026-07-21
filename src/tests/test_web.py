from __future__ import annotations

import pytest

from echotools.media.web.utils import json_body, safe_flush


def test_json_body_roundtrip() -> None:
    assert json_body({"msg": "hello"}) == b'{"msg": "hello"}'


def test_safe_flush_splits_buffer() -> None:
    from echotools.exec.fncall import get_protocol

    proto = get_protocol("entml")
    flushed_safe, flushed_remain = safe_flush("hello", proto)
    assert flushed_safe == "hello"
    assert flushed_remain == ""


@pytest.mark.http
def test_web_application_requires_aiohttp() -> None:
    pytest.importorskip("aiohttp")
    from echotools.media.web import WebApplication

    app = WebApplication()
    assert app.app is not None


@pytest.mark.http
def test_json_response() -> None:
    pytest.importorskip("aiohttp")
    from echotools.media.web.utils import json_response

    resp = json_response({"ok": True}, status=201)
    assert resp.status == 201


@pytest.mark.http
def test_clean_fncall() -> None:
    pytest.importorskip("aiohttp")
    from echotools.exec.fncall import get_protocol
    from echotools.media.web.utils import clean_fncall

    proto = get_protocol("entml")
    text = '<entml:function_calls></entml:function_calls>hello'
    cleaned = clean_fncall(text, proto)
    assert "hello" in cleaned
