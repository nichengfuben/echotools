from __future__ import annotations

"""macOS CoreAudio audio session monitor with ps/lsof fallbacks."""

import ctypes
import ctypes.util
import os
import subprocess
from ctypes import POINTER, Structure, byref, c_void_p, sizeof

from echotools.plat.capture.audio_monitor.types import AudioProcess

_ca_path = (
    ctypes.util.find_library("CoreAudio")
    or "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
)
_CA = ctypes.CDLL(_ca_path)

kAudioObjectSystemObject = 1
kAudioObjectPropertyScopeGlobal = 0x676C6F62
kAudioObjectPropertyElementMaster = 0
kAudioHardwarePropertyDevices = 0x64657623
kAudioDevicePropertyStreams = 0x73746D23
kAudioDevicePropertyDeviceName = 0x6E616D65
kAudioDevicePropertyScopeOutput = 0x6F757470

OSStatus = ctypes.c_int32
AudioObjectID = ctypes.c_uint32

_ca_available = True

KNOWN_AUDIO = {
    "iTunes", "Music", "Spotify", "QuickTime Player",
    "Safari", "Google Chrome", "Firefox", "VLC",
    "zoom.us", "Slack", "Discord",
}


class AudioObjectPropertyAddress(Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint),
        ("mScope", ctypes.c_uint),
        ("mElement", ctypes.c_uint),
    ]


_CA.AudioObjectGetPropertyDataSize.restype = OSStatus
_CA.AudioObjectGetPropertyDataSize.argtypes = [
    AudioObjectID, POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint, c_void_p, POINTER(ctypes.c_uint),
]
_CA.AudioObjectGetPropertyData.restype = OSStatus
_CA.AudioObjectGetPropertyData.argtypes = [
    AudioObjectID, POINTER(AudioObjectPropertyAddress),
    ctypes.c_uint, c_void_p, POINTER(ctypes.c_uint), c_void_p,
]


def _ca_device_name(device_id: int) -> str:
    prop = AudioObjectPropertyAddress(
        kAudioDevicePropertyDeviceName,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMaster,
    )
    buf = ctypes.create_string_buffer(256)
    bufsz = ctypes.c_uint(256)
    _CA.AudioObjectGetPropertyData(device_id, byref(prop), 0, None, byref(bufsz), buf)
    return buf.value.decode("utf-8", errors="replace")


def _ca_has_streams(device_id: int) -> bool:
    prop = AudioObjectPropertyAddress(
        kAudioDevicePropertyStreams,
        kAudioDevicePropertyScopeOutput,
        kAudioObjectPropertyElementMaster,
    )
    sz = ctypes.c_uint(0)
    st = _CA.AudioObjectGetPropertyDataSize(device_id, byref(prop), 0, None, byref(sz))
    return st == 0 and sz.value > 0


def _ca_active_devices() -> list[str]:
    prop = AudioObjectPropertyAddress(
        kAudioHardwarePropertyDevices,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMaster,
    )
    sz = ctypes.c_uint(0)
    _CA.AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, byref(prop), 0, None, byref(sz))
    n = sz.value // sizeof(AudioObjectID)
    ids = (AudioObjectID * n)()
    sz2 = ctypes.c_uint(sz.value)
    _CA.AudioObjectGetPropertyData(
        kAudioObjectSystemObject, byref(prop), 0, None, byref(sz2), ids
    )
    names: list[str] = []
    for did in ids:
        if _ca_has_streams(did):
            names.append(_ca_device_name(did))
    return names


def _lsof_audiosession() -> list[AudioProcess]:
    try:
        out = subprocess.check_output(
            ["lsof", "/dev/audiosession"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []
    result: list[AudioProcess] = []
    for line in out.decode(errors="replace").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        try:
            pid = int(parts[1])
        except ValueError:
            pid = -1
        result.append(AudioProcess(pid, name, "active"))
    return result


def _ps_audio_processes() -> list[AudioProcess]:
    try:
        out = subprocess.check_output(
            ["ps", "-axo", "pid,comm"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        return []
    result: list[AudioProcess] = []
    for line in out.decode(errors="replace").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        name = os.path.basename(parts[1])
        if any(k.lower() in name.lower() for k in KNOWN_AUDIO):
            result.append(AudioProcess(pid, name, "unknown"))
    return result


def _lsof_audio_processes() -> list[AudioProcess]:
    result = _lsof_audiosession()
    if result:
        return result
    return _ps_audio_processes()


def _ca_get_playing() -> list[AudioProcess]:
    if not _ca_active_devices():
        return []
    return _lsof_audio_processes()


def mac_get_playing() -> list[AudioProcess]:
    global _ca_available
    if _ca_available:
        try:
            return _ca_get_playing()
        except Exception as exc:
            print(f"[!] CoreAudio 失败: {exc}  => 切换 ps 回退")
            _ca_available = False
    return _ps_audio_processes()
