from __future__ import annotations

"""Linux ALSA/OSS audio recording."""

import ctypes
import fcntl
import os
import time
from ctypes import POINTER, byref, c_char_p, c_int, c_uint, c_void_p

from echotools.plat.capture.audio_record.config import AudioRecordConfig
from echotools.plat.capture.shared.platform import load_lib

_alsa = load_lib("asound", "libasound.so.2", "libasound.so")

SND_PCM_STREAM_CAPTURE = 1
SND_PCM_ACCESS_RW_INTERLEAVED = 3
SND_PCM_FORMAT_S16_LE = 2
SND_PCM_FORMAT_S32_LE = 10
EAGAIN = 11

if _alsa:
    _alsa.snd_pcm_open.restype = c_int
    _alsa.snd_pcm_open.argtypes = [POINTER(c_void_p), c_char_p, c_int, c_int]
    _alsa.snd_pcm_set_params.restype = c_int
    _alsa.snd_pcm_set_params.argtypes = [
        c_void_p, c_int, c_int, c_uint, c_uint, c_int, c_uint,
    ]
    _alsa.snd_pcm_readi.restype = ctypes.c_ssize_t
    _alsa.snd_pcm_readi.argtypes = [c_void_p, c_void_p, ctypes.c_ulong]
    _alsa.snd_pcm_recover.restype = c_int
    _alsa.snd_pcm_recover.argtypes = [c_void_p, c_int, c_int]
    _alsa.snd_pcm_close.restype = c_int
    _alsa.snd_pcm_close.argtypes = [c_void_p]
    _alsa.snd_pcm_prepare.restype = c_int
    _alsa.snd_pcm_prepare.argtypes = [c_void_p]
    _alsa.snd_device_name_hint.restype = c_int
    _alsa.snd_device_name_hint.argtypes = [c_int, c_char_p, POINTER(c_void_p)]
    _alsa.snd_device_name_get_hint.restype = c_char_p
    _alsa.snd_device_name_get_hint.argtypes = [c_void_p, c_char_p]
    _alsa.snd_device_name_free_hint.restype = c_int
    _alsa.snd_device_name_free_hint.argtypes = [c_void_p]


def _alsa_list_devices() -> list[tuple[str, str]]:
    if not _alsa:
        return []
    hints = c_void_p()
    rc = _alsa.snd_device_name_hint(-1, b"pcm", byref(hints))
    if rc != 0 or not hints:
        return []
    result: list[tuple[str, str]] = []
    arr = ctypes.cast(hints, POINTER(c_void_p))
    i = 0
    while arr[i]:
        n = _alsa.snd_device_name_get_hint(arr[i], b"NAME")
        d = _alsa.snd_device_name_get_hint(arr[i], b"DESC")
        io = _alsa.snd_device_name_get_hint(arr[i], b"IOID")
        nm = n.decode() if n else ""
        desc = d.decode() if d else ""
        io_s = io.decode() if io else ""
        if io_s in ("", "Input"):
            result.append((nm, desc))
        i += 1
    _alsa.snd_device_name_free_hint(hints)
    return result


def _alsa_find_device(name_hint: str) -> str:
    if name_hint.lower() == "default":
        return "default"
    hint = name_hint.lower()
    for nm, desc in _alsa_list_devices():
        if hint in nm.lower() or hint in desc.lower():
            return nm
    return name_hint


def _alsa_record_device(alsa_dev: str, cfg: AudioRecordConfig) -> bytes:
    if not _alsa:
        raise OSError("libasound 不可用")
    handle = c_void_p()
    rc = _alsa.snd_pcm_open(byref(handle), alsa_dev.encode(), SND_PCM_STREAM_CAPTURE, 0)
    if rc < 0:
        raise OSError(f"snd_pcm_open('{alsa_dev}') 失败 rc={rc}")

    fmt = SND_PCM_FORMAT_S16_LE if cfg.bit_depth == 16 else SND_PCM_FORMAT_S32_LE
    rc = _alsa.snd_pcm_set_params(
        handle, fmt, SND_PCM_ACCESS_RW_INTERLEAVED,
        cfg.channels, cfg.sample_rate, 1, cfg.buffer_ms * 1000,
    )
    if rc < 0:
        _alsa.snd_pcm_close(handle)
        raise OSError(f"snd_pcm_set_params 失败 rc={rc}")

    buf_size = cfg.buffer_frames * cfg.frame_bytes
    buf = ctypes.create_string_buffer(buf_size)
    chunks: list[bytes] = []
    remaining = cfg.total_frames

    while remaining > 0:
        want = min(cfg.buffer_frames, remaining)
        rc = _alsa.snd_pcm_readi(handle, buf, want)
        if rc == -EAGAIN:
            time.sleep(0.001)
            continue
        if rc < 0:
            rc2 = _alsa.snd_pcm_recover(handle, rc, 0)
            if rc2 < 0:
                break
            _alsa.snd_pcm_prepare(handle)
            continue
        chunks.append(bytes(buf[: rc * cfg.frame_bytes]))
        remaining -= rc

    _alsa.snd_pcm_close(handle)
    return b"".join(chunks)


def _oss_record_device(dev_path: str, cfg: AudioRecordConfig) -> bytes:
    SNDCTL_DSP_SETFMT = 0xC0045005
    SNDCTL_DSP_STEREO = 0xC0045003
    SNDCTL_DSP_SPEED = 0xC0045002
    AFMT_S16_LE = 0x10

    fd = os.open(dev_path, os.O_RDONLY)
    try:
        val = ctypes.c_int(AFMT_S16_LE)
        fcntl.ioctl(fd, SNDCTL_DSP_SETFMT, val)
        val = ctypes.c_int(1 if cfg.channels == 2 else 0)
        fcntl.ioctl(fd, SNDCTL_DSP_STEREO, val)
        val = ctypes.c_int(cfg.sample_rate)
        fcntl.ioctl(fd, SNDCTL_DSP_SPEED, val)

        total_bytes = cfg.total_frames * cfg.frame_bytes
        data = b""
        while len(data) < total_bytes:
            chunk = os.read(fd, min(4096, total_bytes - len(data)))
            if not chunk:
                break
            data += chunk
        return data
    finally:
        os.close(fd)


def _record_one_device(name: str, cfg: AudioRecordConfig) -> bytes:
    if _alsa:
        try:
            alsa_dev = _alsa_find_device(name)
            pcm = _alsa_record_device(alsa_dev, cfg)
            print(f"[+] ALSA 录制完成: '{alsa_dev}'  {len(pcm)} bytes")
            return pcm
        except Exception as exc:
            print(f"[!] ALSA 失败: {exc}  => 回退 OSS")

    for dsp in ["/dev/dsp", "/dev/dsp0", "/dev/dsp1", "/dev/sound/dsp"]:
        if not os.path.exists(dsp):
            continue
        try:
            pcm = _oss_record_device(dsp, cfg)
            print(f"[+] OSS 录制完成: '{dsp}'  {len(pcm)} bytes")
            return pcm
        except Exception as exc:
            print(f"[!] OSS({dsp}) 失败: {exc}")
    raise RuntimeError(f"Linux 设备 '{name}' 所有录音方案失败")


def linux_record_session(cfg: AudioRecordConfig) -> list[bytes]:
    names = cfg.device_names if cfg.device_names else ["default"]
    streams: list[bytes] = []
    for name in names:
        print(f"[*] Linux 开始录制设备: '{name}'  ({cfg.record_seconds}s)")
        streams.append(_record_one_device(name, cfg))
    return streams
