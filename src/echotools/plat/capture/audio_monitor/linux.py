from __future__ import annotations

"""Linux PulseAudio/ALSA audio session monitor with multi-tier fallback."""

import ctypes
import os
import re
import subprocess
import time
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_char_p,
    c_int,
    c_uint,
    c_void_p,
)

from echotools.plat.capture.audio_monitor.config import AudioMonitorConfig
from echotools.plat.capture.audio_monitor.types import AudioProcess
from echotools.plat.capture.shared.platform import load_lib

_pulse = load_lib("pulse", "libpulse.so.0", "libpulse.so")
_linux_backend = "pulse_lib"

PA_CONTEXT_READY = 4
PA_CONTEXT_FAILED = 6
PA_CONTEXT_TERMINATED = 7


if _pulse:
    class pa_sample_spec(Structure):
        _fields_ = [("format", c_int), ("rate", c_uint), ("channels", ctypes.c_ubyte)]

    _pulse.pa_mainloop_new.restype = c_void_p
    _pulse.pa_mainloop_get_api.restype = c_void_p
    _pulse.pa_mainloop_get_api.argtypes = [c_void_p]
    _pulse.pa_mainloop_iterate.restype = c_int
    _pulse.pa_mainloop_iterate.argtypes = [c_void_p, c_int, POINTER(c_int)]
    _pulse.pa_mainloop_free.argtypes = [c_void_p]
    _pulse.pa_context_new.restype = c_void_p
    _pulse.pa_context_new.argtypes = [c_void_p, c_char_p]
    _pulse.pa_context_connect.restype = c_int
    _pulse.pa_context_connect.argtypes = [c_void_p, c_char_p, c_int, c_void_p]
    _pulse.pa_context_get_state.restype = c_int
    _pulse.pa_context_get_state.argtypes = [c_void_p]
    _pulse.pa_context_get_sink_input_info_list.restype = c_void_p
    _pulse.pa_context_get_sink_input_info_list.argtypes = [c_void_p, c_void_p, c_void_p]
    _pulse.pa_operation_unref.argtypes = [c_void_p]
    _pulse.pa_context_disconnect.argtypes = [c_void_p]
    _pulse.pa_context_unref.argtypes = [c_void_p]


def _pactl_sink_input_pids() -> list[int]:
    out = subprocess.check_output(
        ["pactl", "list", "sink-inputs"],
        stderr=subprocess.DEVNULL,
        timeout=3,
    )
    pids: list[int] = []
    for line in out.decode(errors="replace").splitlines():
        m = re.search(r'application\.process\.id\s*=\s*"(\d+)"', line)
        if m:
            pids.append(int(m.group(1)))
    return pids


def _wait_pulse_ready(ml, ctx) -> None:
    if _pulse is None:
        raise OSError("libpulse 不可用")
    deadline = time.time() + 5.0
    while time.time() < deadline:
        ret = c_int(0)
        _pulse.pa_mainloop_iterate(ml, 0, byref(ret))
        st = _pulse.pa_context_get_state(ctx)
        if st == PA_CONTEXT_READY:
            return
        if st in (PA_CONTEXT_FAILED, PA_CONTEXT_TERMINATED):
            raise OSError(f"pa_context 失败 state={st}")
    raise OSError("pa_context 超时")


def _parse_sink_input(info_ptr: int) -> AudioProcess | None:
    try:
        idx = c_uint.from_address(info_ptr).value
        off = ctypes.sizeof(c_uint) + (4 if ctypes.sizeof(c_void_p) == 8 else 0)
        name_ptr = c_char_p.from_address(info_ptr + off).value
        name = name_ptr.decode("utf-8", errors="replace") if name_ptr else f"stream_{idx}"
        return AudioProcess(-1, name, "active")
    except Exception:
        return None


def _make_sink_input_cb(result: list[AudioProcess], done_flag: list[bool]):
    SI_CB = CFUNCTYPE(None, c_void_p, c_void_p, c_int, c_void_p)

    def _si_callback(ctx_ptr, info_ptr, eol, userdata):
        if eol:
            done_flag[0] = True
            return
        if not info_ptr:
            return
        ap = _parse_sink_input(info_ptr)
        if ap:
            result.append(ap)

    return SI_CB(_si_callback)


def _poll_mainloop(ml, done_flag: list[bool], timeout: float) -> None:
    if _pulse is None:
        raise OSError("libpulse 不可用")
    deadline = time.time() + timeout
    while not done_flag[0] and time.time() < deadline:
        ret = c_int(0)
        _pulse.pa_mainloop_iterate(ml, 0, byref(ret))


def _enrich_pulse_pids(result: list[AudioProcess]) -> None:
    try:
        pids = _pactl_sink_input_pids()
    except Exception:
        return
    for i, ap in enumerate(result):
        if i >= len(pids):
            break
        ap.pid = pids[i]
        if ap.pid <= 0:
            continue
        try:
            with open(f"/proc/{ap.pid}/comm") as f:
                ap.name = f.read().strip()
        except OSError:
            pass


def _pulse_get_playing() -> list[AudioProcess]:
    if not _pulse:
        raise OSError("libpulse 不可用")
    ml = _pulse.pa_mainloop_new()
    api = _pulse.pa_mainloop_get_api(ml)
    ctx = _pulse.pa_context_new(api, b"audio_monitor")
    _pulse.pa_context_connect(ctx, None, 0, None)
    _wait_pulse_ready(ml, ctx)

    result: list[AudioProcess] = []
    done_flag = [False]
    c_cb = _make_sink_input_cb(result, done_flag)
    op = _pulse.pa_context_get_sink_input_info_list(ctx, c_cb, None)
    _poll_mainloop(ml, done_flag, 3.0)
    if op:
        _pulse.pa_operation_unref(op)
    _pulse.pa_context_disconnect(ctx)
    _pulse.pa_context_unref(ctx)
    _pulse.pa_mainloop_free(ml)
    _enrich_pulse_pids(result)
    return result


def _pactl_get_playing(cfg: AudioMonitorConfig) -> list[AudioProcess]:
    try:
        out = subprocess.check_output(
            ["pactl", "list", "sink-inputs"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise OSError("pactl 不可用") from exc

    result: list[AudioProcess] = []
    pid, name, muted = -1, "", False
    for line in out.decode(errors="replace").splitlines():
        line = line.strip()
        m = re.search(r'application\.process\.id\s*=\s*"(\d+)"', line)
        if m:
            pid = int(m.group(1))
        m = re.search(r'application\.name\s*=\s*"(.+)"', line)
        if m:
            name = m.group(1)
        m = re.search(r"Mute:\s*(yes|no)", line)
        if m:
            muted = m.group(1) == "yes"
        if pid > 0 and name:
            proc_name = name
            try:
                with open(f"/proc/{pid}/comm") as f:
                    proc_name = f.read().strip()
            except OSError:
                pass
            state = "inactive" if muted else "active"
            if not cfg.active_state_only or state == "active":
                result.append(AudioProcess(pid, proc_name, state))
            pid, name, muted = -1, "", False
    return result


def _lsof_snd_get_playing() -> list[AudioProcess]:
    try:
        out = subprocess.check_output(
            ["lsof", "+D", "/dev/snd"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise OSError("lsof /dev/snd 失败") from exc
    result: list[AudioProcess] = []
    seen: set[int] = set()
    for line in out.decode(errors="replace").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        if pid in seen:
            continue
        seen.add(pid)
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
        except OSError:
            name = parts[0]
        result.append(AudioProcess(pid, name, "unknown"))
    return result


def _read_running_pid(status_path: str) -> AudioProcess | None:
    try:
        with open(status_path) as f:
            content = f.read()
    except OSError:
        return None
    if "RUNNING" not in content:
        return None
    m = re.search(r"owner_pid\s*:\s*(\d+)", content)
    if not m:
        return None
    pid = int(m.group(1))
    try:
        with open(f"/proc/{pid}/comm") as f:
            name = f.read().strip()
    except OSError:
        name = f"pid_{pid}"
    return AudioProcess(pid, name, "active")


def _scan_pcm_dir(pcm_path: str, result: list[AudioProcess]) -> None:
    for sub_entry in os.listdir(pcm_path):
        status_path = os.path.join(pcm_path, sub_entry, "status")
        if not os.path.isfile(status_path):
            continue
        ap = _read_running_pid(status_path)
        if ap:
            result.append(ap)


def _proc_snd_get_playing() -> list[AudioProcess]:
    result: list[AudioProcess] = []
    asound = "/proc/asound"
    if not os.path.isdir(asound):
        return result
    for card_entry in os.listdir(asound):
        card_path = os.path.join(asound, card_entry)
        if not (card_entry.startswith("card") and os.path.isdir(card_path)):
            continue
        for pcm_entry in os.listdir(card_path):
            pcm_path = os.path.join(card_path, pcm_entry)
            if not (pcm_entry.startswith("pcm") and os.path.isdir(pcm_path)):
                continue
            _scan_pcm_dir(pcm_path, result)
    return result


def linux_get_playing(cfg: AudioMonitorConfig) -> list[AudioProcess]:
    global _linux_backend
    if _linux_backend == "pulse_lib":
        try:
            return _pulse_get_playing()
        except Exception as exc:
            print(f"[!] libpulse 失败: {exc}  => 切换 pactl")
            _linux_backend = "pactl"
    if _linux_backend == "pactl":
        try:
            return _pactl_get_playing(cfg)
        except Exception as exc:
            print(f"[!] pactl 失败: {exc}  => 切换 lsof")
            _linux_backend = "lsof"
    if _linux_backend == "lsof":
        try:
            return _lsof_snd_get_playing()
        except Exception as exc:
            print(f"[!] lsof 失败: {exc}  => 切换 /proc/asound")
            _linux_backend = "proc"
    return _proc_snd_get_playing()
