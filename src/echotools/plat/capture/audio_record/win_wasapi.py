from __future__ import annotations

"""Windows WASAPI audio recording."""

import ctypes
import ctypes.wintypes as wt
import time
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_uint,
    c_ulong,
    c_ushort,
    c_void_p,
)

from echotools.plat.capture.audio_record.config import AudioRecordConfig
from echotools.plat.capture.shared.pcm import resample_pcm
from echotools.plat.capture.shared.win_com import GUID, com_call, com_release, make_guid

CLSID_MM = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_ENUM = "A95664D2-9614-4F35-A746-DE8DB63617E6"
IID_CLIENT = "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"
IID_CAPTURE = "C8ADBD64-E71E-48A0-A4DE-185C395CD317"

CLSCTX_ALL = 0x17
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_SHAREMODE_SHARED = 0
DEVICE_STATE_ACTIVE = 0x1
eRender = 0
eCapture = 1
eConsole = 0
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
HRESULT = ctypes.c_long

CLSID_MMDeviceEnumerator = make_guid(CLSID_MM)
IID_IMMDeviceEnumerator = make_guid(IID_ENUM)
IID_IAudioClient = make_guid(IID_CLIENT)
IID_IAudioCaptureClient = make_guid(IID_CAPTURE)

_ole32 = ctypes.WinDLL("ole32")
_ole32.CoInitialize.argtypes = [c_void_p]
_ole32.CoInitialize.restype = HRESULT
_ole32.CoCreateInstance.argtypes = [
    POINTER(GUID), c_void_p, c_ulong, POINTER(GUID), POINTER(c_void_p),
]
_ole32.CoCreateInstance.restype = HRESULT
_ole32.CoTaskMemFree.argtypes = [c_void_p]


class WAVEFORMATEX(Structure):
    _fields_ = [
        ("wFormatTag", c_ushort), ("nChannels", c_ushort),
        ("nSamplesPerSec", c_ulong), ("nAvgBytesPerSec", c_ulong),
        ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort),
        ("cbSize", c_ushort),
    ]


def _get_enumerator():
    _ole32.CoInitialize(None)
    enumerator = c_void_p()
    hr = _ole32.CoCreateInstance(
        byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
        byref(IID_IMMDeviceEnumerator), byref(enumerator),
    )
    if hr != 0:
        raise OSError(f"CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}")
    return enumerator


def _enum_devices(enumerator) -> list[tuple[str, c_void_p, int]]:
    result: list[tuple[str, c_void_p, int]] = []
    for flow in (eCapture, eRender):
        coll = c_void_p()
        hr = com_call(
            enumerator, 4, HRESULT, [c_uint, c_uint, POINTER(c_void_p)],
            flow, DEVICE_STATE_ACTIVE, byref(coll),
        )
        if hr != 0:
            continue
        count = c_uint(0)
        com_call(coll, 3, HRESULT, [POINTER(c_uint)], byref(count))
        for i in range(count.value):
            dev = c_void_p()
            hr = com_call(coll, 4, HRESULT, [c_uint, POINTER(c_void_p)], i, byref(dev))
            if hr != 0:
                continue
            pwstr = c_void_p()
            com_call(dev, 5, HRESULT, [POINTER(c_void_p)], byref(pwstr))
            name = ctypes.wstring_at(pwstr) if pwstr else f"device_{flow}_{i}"
            _ole32.CoTaskMemFree(pwstr)
            result.append((name, dev, flow))
        com_release(coll)
    return result


def _find_device(enumerator, name_hint: str):
    if name_hint.lower() == "default":
        dev = c_void_p()
        hr = com_call(
            enumerator, 4, HRESULT, [c_uint, c_uint, POINTER(c_void_p)],
            eCapture, eConsole, byref(dev),
        )
        if hr != 0:
            raise OSError(f"GetDefaultAudioEndpoint hr=0x{hr & 0xFFFFFFFF:08X}")
        return dev, eCapture
    hint = name_hint.lower()
    devs = _enum_devices(enumerator)
    for nm, dev, flow in devs:
        if hint in nm.lower():
            for nm2, dev2, _ in devs:
                if dev2 != dev:
                    com_release(dev2)
            return dev, flow
    raise OSError(f"找不到匹配设备: '{name_hint}'")


def _capture_loop(cc, ac, cfg: AudioRecordConfig, dev_rate, dev_ch, dev_bits, flow) -> bytes:
    bytes_per_frame = dev_ch * (dev_bits // 8)
    raw_chunks: list[bytes] = []
    total = 0
    target = int(dev_rate * cfg.record_seconds)
    com_call(ac, 11, HRESULT, [])

    while total < target:
        time.sleep(cfg.buffer_ms / 1000.0 / 2)
        next_pkt = c_uint(0)
        com_call(cc, 3, HRESULT, [POINTER(c_uint)], byref(next_pkt))
        while next_pkt.value > 0:
            data_ptr = c_void_p()
            frames = c_uint(0)
            flags_out = wt.DWORD(0)
            hr = com_call(
                cc, 0, HRESULT,
                [POINTER(c_void_p), POINTER(c_uint), POINTER(wt.DWORD), c_void_p, c_void_p],
                byref(data_ptr), byref(frames), byref(flags_out), None, None,
            )
            if hr != 0:
                break
            n = frames.value
            silent = bool(flags_out.value & AUDCLNT_BUFFERFLAGS_SILENT)
            if silent or not data_ptr.value:
                raw_chunks.append(b"\x00" * n * bytes_per_frame)
            else:
                raw_chunks.append(ctypes.string_at(data_ptr.value, n * bytes_per_frame))
            com_call(cc, 2, HRESULT, [c_uint], n)
            total += n
            com_call(cc, 3, HRESULT, [POINTER(c_uint)], byref(next_pkt))

    com_call(ac, 12, HRESULT, [])
    return b"".join(raw_chunks)


def wasapi_record_device(device_ptr, flow: int, cfg: AudioRecordConfig) -> bytes:
    ac = c_void_p()
    hr = com_call(
        device_ptr, 3, HRESULT,
        [POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p)],
        byref(IID_IAudioClient), CLSCTX_ALL, None, byref(ac),
    )
    if hr != 0:
        raise OSError(f"Activate hr=0x{hr & 0xFFFFFFFF:08X}")

    pwfx = c_void_p()
    hr = com_call(ac, 8, HRESULT, [POINTER(c_void_p)], byref(pwfx))
    if hr != 0:
        raise OSError(f"GetMixFormat hr=0x{hr & 0xFFFFFFFF:08X}")

    wfx = WAVEFORMATEX.from_address(pwfx.value)
    dev_rate, dev_ch, dev_bits = wfx.nSamplesPerSec, wfx.nChannels, wfx.wBitsPerSample
    flags = AUDCLNT_STREAMFLAGS_LOOPBACK if flow == eRender else 0
    buf_dur = int(cfg.buffer_ms * 10000)
    hr = com_call(
        ac, 3, HRESULT,
        [c_uint, c_uint, ctypes.c_int64, ctypes.c_int64, POINTER(WAVEFORMATEX), c_void_p],
        AUDCLNT_SHAREMODE_SHARED, flags, buf_dur, 0, pwfx, None,
    )
    _ole32.CoTaskMemFree(pwfx)
    if hr != 0:
        com_release(ac)
        raise OSError(f"Initialize hr=0x{hr & 0xFFFFFFFF:08X}")

    cc = c_void_p()
    hr = com_call(ac, 14, HRESULT, [POINTER(GUID), POINTER(c_void_p)], byref(IID_IAudioCaptureClient), byref(cc))
    if hr != 0:
        com_release(ac)
        raise OSError(f"GetService hr=0x{hr & 0xFFFFFFFF:08X}")

    try:
        raw = _capture_loop(cc, ac, cfg, dev_rate, dev_ch, dev_bits, flow)
    finally:
        com_release(cc)
        com_release(ac)

    return resample_pcm(
        raw, dev_rate, dev_ch, dev_bits,
        cfg.sample_rate, cfg.channels, cfg.bit_depth,
    )


def wasapi_record_name(name: str, cfg: AudioRecordConfig) -> bytes:
    enum = _get_enumerator()
    try:
        dev, flow = _find_device(enum, name)
        try:
            return wasapi_record_device(dev, flow, cfg)
        finally:
            com_release(dev)
    finally:
        com_release(enum)
