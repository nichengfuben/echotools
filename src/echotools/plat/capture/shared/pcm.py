from __future__ import annotations

"""PCM mixing and resampling utilities."""

import struct

__all__ = ["clamp", "mix_streams", "resample_pcm"]


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def mix_streams(
    streams: list[bytes],
    depth: int,
    mix_normalize: bool = True,
) -> bytes:
    """Mix multiple equal-format PCM byte streams via weighted average."""
    if not streams:
        return b""
    if len(streams) == 1:
        return streams[0]

    n_bytes = depth // 8
    count = max(len(s) for s in streams) // n_bytes
    n = len(streams)
    padded = [s + b"\x00" * (count * n_bytes - len(s)) for s in streams]
    fmt = "<h" if depth == 16 else "<i"
    pack_fmt = f"<{count}{'h' if depth == 16 else 'i'}"
    clip = (1 << (depth - 1)) - 1
    lo = -(1 << (depth - 1))

    sums = [0] * count
    for stream in padded:
        samples = struct.unpack_from(pack_fmt, stream)
        for i, v in enumerate(samples):
            sums[i] += v

    if mix_normalize:
        peak = max(abs(v) for v in sums) if sums else 1
        scale = clip / peak if peak > clip else 1.0
    else:
        scale = 1.0 / n

    mixed = bytearray(count * n_bytes)
    for i, v in enumerate(sums):
        val = int(v * scale)
        val = clamp(val, lo, clip)
        struct.pack_into(fmt, mixed, i * n_bytes, val)
    return bytes(mixed)


def _frames_from_samples(
    samples: tuple[int, ...],
    n_src: int,
    src_ch: int,
    dst_ch: int,
) -> list[tuple[int, ...]]:
    frames: list[tuple[int, ...]] = []
    for i in range(n_src):
        frame = samples[i * src_ch : i * src_ch + src_ch]
        if dst_ch == 1:
            frames.append((sum(frame) // len(frame),))
        elif dst_ch == 2:
            if src_ch == 1:
                frames.append((frame[0], frame[0]))
            else:
                frames.append((frame[0], frame[1]))
        else:
            frames.append(tuple(frame[:dst_ch]))
    return frames


def _interpolate_frames(
    frames: list[tuple[int, ...]],
    n_src: int,
    dst_rate: int,
    src_rate: int,
    dst_ch: int,
    src_bits: int,
    dst_bits: int,
    s_clip: int,
    d_clip: int,
    d_lo: int,
) -> list[int]:
    ratio = src_rate / dst_rate
    n_dst = int(n_src / ratio)
    d_fmt_vals: list[int] = []
    for j in range(n_dst):
        pos = j * ratio
        idx = int(pos)
        frac = pos - idx
        idx1 = min(idx + 1, n_src - 1)
        for c in range(dst_ch):
            v0 = frames[idx][c]
            v1 = frames[idx1][c]
            val = int(v0 + frac * (v1 - v0))
            if src_bits != dst_bits:
                val = val * d_clip // s_clip
            d_fmt_vals.append(clamp(val, d_lo, d_clip))
    return d_fmt_vals


def resample_pcm(
    data: bytes,
    src_rate: int,
    src_ch: int,
    src_bits: int,
    dst_rate: int,
    dst_ch: int,
    dst_bits: int,
) -> bytes:
    """Linear-interpolation resample with channel and bit-depth conversion."""
    if src_rate == dst_rate and src_ch == dst_ch and src_bits == dst_bits:
        return data

    s_fmt = "h" if src_bits == 16 else "i"
    d_fmt = "h" if dst_bits == 16 else "i"
    s_bytes = src_bits // 8
    s_clip = (1 << (src_bits - 1)) - 1
    d_clip = (1 << (dst_bits - 1)) - 1
    d_lo = -(1 << (dst_bits - 1))
    n_src = len(data) // (s_bytes * src_ch)
    samples = struct.unpack_from(f"<{n_src * src_ch}{s_fmt}", data)
    frames = _frames_from_samples(samples, n_src, src_ch, dst_ch)
    out = _interpolate_frames(
        frames, n_src, dst_rate, src_rate, dst_ch, src_bits, dst_bits, s_clip, d_clip, d_lo
    )
    return struct.pack(f"<{len(out)}{d_fmt}", *out)
