from __future__ import annotations

"""Windows audio session monitor (WASAPI with winmm fallback)."""

import ctypes
import ctypes.wintypes as wt
import os
from ctypes import POINTER, byref, c_int, c_uint, c_void_p, c_wchar_p, sizeof

from echotools.plat.capture.audio_monitor.config import AudioMonitorConfig
from echotools.plat.capture.audio_monitor.types import AudioProcess
from echotools.plat.capture.shared.win_com import (
    GUID,
    com_call,
    com_qi,
    com_release,
    make_guid,
)

CLSID_MM = "BCDE0395-E52F-467C-8E3D-C4579291692E"
IID_ENUM = "A95664D2-9614-4F35-A746-DE8DB63617E6"
IID_ASM2 = "77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"
IID_ASC2 = "BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"
IID_SAV = "87CE5498-68D6-44E5-9215-6DA47EF883D8"

AudioSessionStateActive = 1
eRender = 0
eConsole = 0
CLSCTX_ALL = 0x17
PROCESS_QUERY_LIMITED = 0x1000
PROCESS_ALL = 0x1F0FFF
HRESULT = ctypes.c_long

_CLSID = make_guid(CLSID_MM)
_IID_ENUM = make_guid(IID_ENUM)
_IID_ASM2 = make_guid(IID_ASM2)
_IID_ASC2 = make_guid(IID_ASC2)
_IID_SAV = make_guid(IID_SAV)

_ole32 = ctypes.WinDLL("ole32")
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_winmm = ctypes.WinDLL("winmm")
_winmm.waveOutGetNumDevs.restype = ctypes.c_uint
_ole32.CoInitializeEx(None, 0)

_wasapi_available = True


def _pid_to_name(pid: int) -> str:
    if pid <= 0:
        return "<system>"
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return f"<pid {pid}>"
    buf = ctypes.create_unicode_buffer(512)
    size = wt.DWORD(512)
    ok = _kernel32.QueryFullProcessImageNameW(h, 0, buf, byref(size))
    _kernel32.CloseHandle(h)
    if ok and buf.value:
        return os.path.basename(buf.value)
    return f"<pid {pid}>"


def _read_volume(sc_ptr) -> float:
    try:
        sav = com_qi(sc_ptr, _IID_SAV)
        fvol = ctypes.c_float(0.0)
        com_call(sav, 3, HRESULT, [POINTER(ctypes.c_float)], byref(fvol))
        com_release(sav)
        return round(fvol.value, 3)
    except OSError:
        return -1.0


def _state_str(val: int) -> str:
    return {0: "inactive", 1: "active", 2: "expired"}.get(val, "unknown")


def _one_session(se_ptr, idx: int, cfg: AudioMonitorConfig) -> AudioProcess | None:
    sc = c_void_p()
    hr = com_call(se_ptr, 4, HRESULT, [c_int, POINTER(c_void_p)], idx, byref(sc))
    if hr != 0 or not sc:
        return None
    try:
        sc2 = com_qi(sc, _IID_ASC2)
    except OSError:
        com_release(sc)
        return None
    try:
        state = c_int(-1)
        com_call(sc2, 3, HRESULT, [POINTER(c_int)], byref(state))
        if cfg.active_state_only and state.value != AudioSessionStateActive:
            return None
        pid = wt.DWORD(0)
        com_call(sc2, 14, HRESULT, [POINTER(wt.DWORD)], byref(pid))
        return AudioProcess(
            pid.value,
            _pid_to_name(pid.value),
            _state_str(state.value),
            _read_volume(sc),
        )
    finally:
        com_release(sc2)
        com_release(sc)


def _wasapi_get_playing(cfg: AudioMonitorConfig) -> list[AudioProcess]:
    enumerator = c_void_p()
    hr = _ole32.CoCreateInstance(
        byref(_CLSID), None, CLSCTX_ALL, byref(_IID_ENUM), byref(enumerator)
    )
    if hr != 0:
        raise OSError(f"CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}")

    device = c_void_p()
    hr = com_call(
        enumerator, 4, HRESULT, [c_uint, c_uint, POINTER(c_void_p)],
        eRender, eConsole, byref(device),
    )
    com_release(enumerator)
    if hr != 0:
        raise OSError(f"GetDefaultAudioEndpoint hr=0x{hr & 0xFFFFFFFF:08X}")

    asm2 = c_void_p()
    hr = com_call(
        device, 3, HRESULT,
        [POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p)],
        byref(_IID_ASM2), CLSCTX_ALL, None, byref(asm2),
    )
    com_release(device)
    if hr != 0:
        raise OSError(f"Activate hr=0x{hr & 0xFFFFFFFF:08X}")

    se = c_void_p()
    hr = com_call(asm2, 5, HRESULT, [POINTER(c_void_p)], byref(se))
    com_release(asm2)
    if hr != 0:
        raise OSError(f"GetSessionEnumerator hr=0x{hr & 0xFFFFFFFF:08X}")

    try:
        count = c_int(0)
        com_call(se, 3, HRESULT, [POINTER(c_int)], byref(count))
        result: list[AudioProcess] = []
        for i in range(count.value):
            proc = _one_session(se, i, cfg)
            if proc is not None:
                result.append(proc)
        return result
    finally:
        com_release(se)


def _winmm_get_playing() -> list[AudioProcess]:
    if _winmm.waveOutGetNumDevs() == 0:
        return []
    _psapi.EnumProcesses.restype = wt.BOOL
    _psapi.EnumProcesses.argtypes = [POINTER(wt.DWORD), wt.DWORD, POINTER(wt.DWORD)]
    _psapi.GetModuleBaseNameW.restype = wt.DWORD
    _psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HANDLE, c_wchar_p, wt.DWORD]
    _psapi.EnumProcessModules.restype = wt.BOOL
    _psapi.EnumProcessModules.argtypes = [
        wt.HANDLE, POINTER(wt.HANDLE), wt.DWORD, POINTER(wt.DWORD),
    ]
    buf = (wt.DWORD * 4096)()
    cb = wt.DWORD(0)
    _psapi.EnumProcesses(buf, sizeof(buf), byref(cb))
    n_proc = cb.value // sizeof(wt.DWORD)
    result: list[AudioProcess] = []
    for i in range(n_proc):
        pid = buf[i]
        if pid == 0:
            continue
        h = _kernel32.OpenProcess(PROCESS_ALL, False, pid)
        if not h:
            continue
        mods = (wt.HANDLE * 256)()
        cb2 = wt.DWORD(0)
        ok = _psapi.EnumProcessModules(h, mods, sizeof(mods), byref(cb2))
        if not ok:
            _kernel32.CloseHandle(h)
            continue
        n_mods = cb2.value // sizeof(wt.HANDLE)
        name_buf = ctypes.create_unicode_buffer(256)
        found = False
        for j in range(n_mods):
            _psapi.GetModuleBaseNameW(h, mods[j], name_buf, 256)
            low = name_buf.value.lower()
            if "winmm" in low or "audioses" in low:
                found = True
                break
        _kernel32.CloseHandle(h)
        if found:
            result.append(AudioProcess(pid, _pid_to_name(pid), "unknown"))
    return result


def win_get_playing(cfg: AudioMonitorConfig) -> list[AudioProcess]:
    global _wasapi_available
    if _wasapi_available:
        try:
            return _wasapi_get_playing(cfg)
        except Exception as exc:
            print(f"[!] WASAPI 失败: {exc}  => 切换 winmm 回退")
            _wasapi_available = False
    return _winmm_get_playing()
