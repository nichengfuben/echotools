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
from echotools.plat.capture.shared.win_com import (
    GUID,
    com_call,
    com_qi,
    com_release,
    make_guid,
)

__all__ = [
    "GUID",
    "IS_LINUX",
    "IS_MACOS",
    "IS_WINDOWS",
    "_OS",
    "clamp",
    "com_call",
    "com_qi",
    "com_release",
    "load_lib",
    "make_guid",
    "mix_streams",
    "resample_pcm",
    "rgba_to_bgra",
    "write_bmp",
    "write_wav",
]
