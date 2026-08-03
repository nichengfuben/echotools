from __future__ import annotations

"""PCM WAV writer (stdlib only, no wave module)."""

import struct


def write_wav(path: str, pcm: bytes, rate: int, ch: int, depth: int) -> None:
    """Write a standard PCM WAV file."""
    bps = depth // 8
    block_align = ch * bps
    byte_rate = rate * block_align
    data_size = len(pcm)
    file_size = 36 + data_size
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", file_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(
            struct.pack(
                "<IHHIIHH",
                16,
                1,
                ch,
                rate,
                byte_rate,
                block_align,
                depth,
            )
        )
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm)
