from __future__ import annotations

"""Windows winmm waveIn audio recording fallback."""

import ctypes
import ctypes.wintypes as wt
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_char,
    c_char_p,
    c_uint,
    c_ulong,
    c_ushort,
    c_void_p,
)

from echotools.plat.capture.audio_record.config import AudioRecordConfig

WAVE_FORMAT_PCM = 1
CALLBACK_NULL = 0x0

_winmm = ctypes.WinDLL("winmm")
_winmm.waveInGetNumDevs.restype = ctypes.c_uint
_winmm.waveInGetDevCapsA.argtypes = [c_uint, c_void_p, c_uint]
_winmm.waveInGetDevCapsA.restype = c_uint
_winmm.waveInOpen.restype = c_uint
_winmm.waveInOpen.argtypes = [
    POINTER(c_void_p), c_uint, c_void_p, c_ulong, c_ulong, c_ulong,
]
_winmm.waveInPrepareHeader.argtypes = [c_void_p, c_void_p, c_uint]
_winmm.waveInPrepareHeader.restype = c_uint
_winmm.waveInAddBuffer.argtypes = [c_void_p, c_void_p, c_uint]
_winmm.waveInAddBuffer.restype = c_uint
_winmm.waveInStart.argtypes = [c_void_p]
_winmm.waveInStart.restype = c_uint
_winmm.waveInStop.argtypes = [c_void_p]
_winmm.waveInStop.restype = c_uint
_winmm.waveInReset.argtypes = [c_void_p]
_winmm.waveInUnprepareHeader.argtypes = [c_void_p, c_void_p, c_uint]
_winmm.waveInClose.argtypes = [c_void_p]


class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", c_ushort), ("nChannels", c_ushort),
        ("nSamplesPerSec", c_ulong), ("nAvgBytesPerSec", c_ulong),
        ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort),
        ("cbSize", c_ushort),
    ]


class WAVEHDR(Structure):
    _fields_ = [
        ("lpData", c_char_p), ("dwBufferLength", wt.DWORD),
        ("dwBytesRecorded", wt.DWORD), ("dwUser", c_ulong),
        ("dwFlags", wt.DWORD), ("dwLoops", wt.DWORD),
        ("lpNext", c_void_p), ("reserved", c_ulong),
    ]


class WAVEINCAPS(Structure):
    _fields_ = [
        ("wMid", c_ushort), ("wPid", c_ushort),
        ("vDriverVersion", c_ulong), ("szPname", c_char * 32),
        ("dwFormats", wt.DWORD), ("wChannels", c_ushort),
        ("wReserved1", c_ushort),
    ]


def _find_device_id(name_hint: str) -> int:
    if name_hint.lower() == "default":
        return 0
    n = _winmm.waveInGetNumDevs()
    hint = name_hint.lower()
    caps = WAVEINCAPS()
    for i in range(n):
        _winmm.waveInGetDevCapsA(i, byref(caps), ctypes.sizeof(WAVEINCAPS))
        nm = caps.szPname.decode("gbk", errors="replace").lower()
        if hint in nm:
            return i
    return 0


def winmm_record_device(dev_id: int, cfg: AudioRecordConfig) -> bytes:
    wfx = WAVEFORMATEX()
    wfx.wFormatTag = WAVE_FORMAT_PCM
    wfx.nChannels = cfg.channels
    wfx.nSamplesPerSec = cfg.sample_rate
    wfx.wBitsPerSample = cfg.bit_depth
    wfx.nBlockAlign = cfg.frame_bytes
    wfx.nAvgBytesPerSec = cfg.sample_rate * cfg.frame_bytes
    wfx.cbSize = 0

    h_wave = c_void_p()
    rc = _winmm.waveInOpen(byref(h_wave), dev_id, byref(wfx), 0, 0, CALLBACK_NULL)
    if rc != 0:
        raise OSError(f"waveInOpen 失败 rc={rc}")

    buf_size = cfg.buffer_frames * cfg.frame_bytes
    n_bufs = max(4, int(cfg.record_seconds * 1000 / cfg.buffer_ms) + 2)
    raw_bufs = [ctypes.create_string_buffer(buf_size) for _ in range(n_bufs)]
    hdrs: list[WAVEHDR] = []

    for buf in raw_bufs:
        hdr = WAVEHDR()
        hdr.lpData = ctypes.cast(buf, c_char_p)
        hdr.dwBufferLength = buf_size
        hdrs.append(hdr)
        _winmm.waveInPrepareHeader(h_wave, byref(hdr), ctypes.sizeof(WAVEHDR))
        _winmm.waveInAddBuffer(h_wave, byref(hdr), ctypes.sizeof(WAVEHDR))

    _winmm.waveInStart(h_wave)
    time.sleep(cfg.record_seconds)
    _winmm.waveInStop(h_wave)
    _winmm.waveInReset(h_wave)

    chunks: list[bytes] = []
    for hdr, buf in zip(hdrs, raw_bufs):
        if hdr.dwBytesRecorded > 0:
            chunks.append(bytes(buf[: hdr.dwBytesRecorded]))
        _winmm.waveInUnprepareHeader(h_wave, byref(hdr), ctypes.sizeof(WAVEHDR))
    _winmm.waveInClose(h_wave)
    return b"".join(chunks)


def winmm_record_name(name: str, cfg: AudioRecordConfig) -> bytes:
    dev_id = _find_device_id(name)
    return winmm_record_device(dev_id, cfg)
