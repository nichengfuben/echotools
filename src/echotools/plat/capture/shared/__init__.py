from __future__ import annotations

from echotools.plat.capture.shared.bmp import rgba_to_bgra, write_bmp
from echotools.plat.capture.shared.pcm import clamp, mix_streams, resample_pcm
from echotools.plat.capture.shared.platform import (
    _OS,
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    load_lib,
)
from echotools.plat.capture.shared.wav import write_wav

if IS_WINDOWS:
    from echotools.plat.capture.shared.win_com import (
        GUID,
        com_call,
        com_qi,
        com_release,
        make_guid,
    )

__all__ = [
    "IS_LINUX",
    "IS_MACOS",
    "IS_WINDOWS",
    "_OS",
    "clamp",
    "load_lib",
    "mix_streams",
    "resample_pcm",
    "rgba_to_bgra",
    "write_bmp",
    "write_wav",
]
if IS_WINDOWS:
    __all__ += ["GUID", "com_call", "com_qi", "com_release", "make_guid"]
