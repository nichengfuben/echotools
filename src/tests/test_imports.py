from __future__ import annotations

"""Import portability tests."""


def test_core_import_without_optional_deps() -> None:
    import echotools

    assert echotools.__version__
    assert echotools.EchoTools is not None
    assert echotools.json_body({"ok": True}) == b'{"ok": true}'


def test_lazy_web_application_import() -> None:
    import echotools

    try:
        import aiohttp  # noqa: F401
    except ImportError:
        import pytest

        with pytest.raises(ImportError, match="aiohttp"):
            _ = echotools.WebApplication
        return

    assert echotools.WebApplication is not None


def test_lazy_fncall_exports() -> None:
    import echotools

    assert echotools.get_protocol is not None
    assert echotools.inject_fncall is not None
