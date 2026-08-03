from __future__ import annotations

"""Portable multi-device audio recording API."""

import sys

from echotools.plat.capture.audio_record.config import AudioRecordConfig
from echotools.plat.capture.shared.pcm import mix_streams
from echotools.plat.capture.shared.platform import _OS, IS_LINUX, IS_MACOS, IS_WINDOWS
from echotools.plat.capture.shared.wav import write_wav

if IS_WINDOWS:
    from echotools.plat.capture.audio_record.win import win_record_session
elif IS_MACOS:
    from echotools.plat.capture.audio_record.mac import mac_record_session
elif IS_LINUX:
    from echotools.plat.capture.audio_record.linux import linux_record_session


def record_audio_session(config: AudioRecordConfig | None = None) -> str:
    """Record from configured devices, mix, and write WAV. Returns output path."""
    cfg = config or AudioRecordConfig()
    py_ver = sys.version_info
    print(f"[*] 平台: {_OS} | Python {py_ver.major}.{py_ver.minor}")
    print(f"[*] 设备列表: {cfg.device_names}")
    print(
        f"[*] 参数: {cfg.sample_rate}Hz / {cfg.channels}ch / "
        f"{cfg.bit_depth}bit / {cfg.record_seconds}s"
    )
    print(f"[*] 输出: {cfg.output_path}")

    if IS_WINDOWS:
        streams = win_record_session(cfg)
    elif IS_MACOS:
        streams = mac_record_session(cfg)
    elif IS_LINUX:
        streams = linux_record_session(cfg)
    else:
        raise RuntimeError(f"不支持的操作系统: {_OS}")

    mixed = mix_streams(streams, cfg.bit_depth, cfg.mix_normalize)
    write_wav(cfg.output_path, mixed, cfg.sample_rate, cfg.channels, cfg.bit_depth)
    print(f"[+] 已写入: {cfg.output_path}  ({len(mixed)} bytes PCM)")
    print("[+] 录音完成")
    return cfg.output_path
