from __future__ import annotations

"""Portable audio session monitor API."""

import sys
import time

from echotools.plat.capture.audio_monitor.config import AudioMonitorConfig
from echotools.plat.capture.audio_monitor.types import AudioProcess
from echotools.plat.capture.shared.platform import _OS, IS_LINUX, IS_MACOS, IS_WINDOWS

if IS_WINDOWS:
    from echotools.plat.capture.audio_monitor.win import win_get_playing
elif IS_MACOS:
    from echotools.plat.capture.audio_monitor.mac import mac_get_playing
elif IS_LINUX:
    from echotools.plat.capture.audio_monitor.linux import linux_get_playing


def get_playing_processes(
    config: AudioMonitorConfig | None = None,
) -> list[AudioProcess]:
    """Return processes currently playing audio."""
    cfg = config or AudioMonitorConfig()
    try:
        if IS_WINDOWS:
            return win_get_playing(cfg)
        if IS_MACOS:
            return mac_get_playing()
        if IS_LINUX:
            return linux_get_playing(cfg)
        raise RuntimeError(f"不支持的平台: {_OS}")
    except Exception as exc:
        print(f"[!] get_playing_processes 异常: {exc}")
        return []


def _format_process(ap: AudioProcess, cfg: AudioMonitorConfig) -> str:
    parts = [f"📢 {ap.name}"]
    if cfg.show_pid and ap.pid > 0:
        parts.append(f"PID={ap.pid}")
    if ap.volume >= 0:
        parts.append(f"vol={ap.volume:.0%}")
    return "  " + " | ".join(parts)


def _print_monitor_update(
    procs: list[AudioProcess],
    cfg: AudioMonitorConfig,
    last_set: set[AudioProcess],
) -> set[AudioProcess]:
    cur_set = set(procs)
    if cfg.print_on_change and cur_set == last_set:
        return last_set
    ts = (
        f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
        if cfg.show_timestamp
        else ""
    )
    print(f"\n{'=' * cfg.banner_width}")
    if ts:
        print(ts)
    if cur_set:
        for ap in sorted(cur_set, key=lambda x: x.name):
            print(_format_process(ap, cfg))
    else:
        print("  🔇 当前没有进程在播放声音")
    return cur_set


def run_audio_monitor(config: AudioMonitorConfig | None = None) -> None:
    """Poll and print playing audio processes until KeyboardInterrupt."""
    cfg = config or AudioMonitorConfig()
    py_ver = sys.version_info
    print("=" * cfg.banner_width)
    print(f"  跨平台音频进程监控器  [{_OS} / Python {py_ver.major}.{py_ver.minor}]")
    print("  实时显示正在播放声音的进程")
    print("  按 Ctrl+C 退出")
    print("=" * cfg.banner_width)

    last_set: set[AudioProcess] = set()
    try:
        while True:
            procs = get_playing_processes(cfg)
            last_set = _print_monitor_update(procs, cfg, last_set)
            time.sleep(cfg.poll_interval_sec)
    except KeyboardInterrupt:
        print("\n\n  监控结束。")
