from __future__ import annotations

"""Package version resolution."""

_FALLBACK_VERSION = "1.0.36"


def get_version() -> str:
    """Return installed package version, with editable-install fallback."""
    try:
        from importlib.metadata import version

        return version("echotools")
    except Exception:
        return _FALLBACK_VERSION
