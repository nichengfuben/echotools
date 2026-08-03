from __future__ import annotations

"""BMP writer and pixel format helpers."""

import struct
from ctypes import c_ubyte


def write_bmp(
    path: str,
    width: int,
    height: int,
    pixel_bytes: bytes,
    top_down: bool = True,
) -> None:
    """Write a 32-bit BMP file."""
    fhs, ihs = 14, 40
    offset = fhs + ihs
    fsize = offset + len(pixel_bytes)
    h_field = -height if top_down else height
    with open(path, "wb") as f:
        f.write(struct.pack("<2sIHHI", b"BM", fsize, 0, 0, offset))
        f.write(
            struct.pack(
                "<IiiHHIIiiII",
                ihs,
                width,
                h_field,
                1,
                32,
                0,
                len(pixel_bytes),
                0,
                0,
                0,
                0,
            )
        )
        f.write(pixel_bytes)


def rgba_to_bgra(data: bytes) -> bytes:
    """Swap R/B channels in RGBA32 pixel data."""
    arr = (c_ubyte * len(data)).from_buffer_copy(data)
    for i in range(0, len(arr), 4):
        arr[i], arr[i + 2] = arr[i + 2], arr[i]
    return bytes(arr)
