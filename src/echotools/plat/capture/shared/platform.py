from __future__ import annotations

"""Runtime platform flags and native library loading."""

import ctypes
import ctypes.util
import platform
from ctypes import CDLL

_OS = platform.system()
IS_WINDOWS = _OS == "Windows"
IS_MACOS = _OS == "Darwin"
IS_LINUX = _OS == "Linux"


def load_lib(*names: str) -> CDLL | None:
    """Try loading a shared library by name list."""
    for name in names:
        try:
            path = ctypes.util.find_library(name) or name
            return CDLL(path, use_errno=True)
        except OSError:
            continue
    return None


__all__ = ["IS_LINUX", "IS_MACOS", "IS_WINDOWS", "_OS", "load_lib"]
