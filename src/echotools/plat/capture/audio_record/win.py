from __future__ import annotations

"""Windows audio recording (WASAPI with winmm fallback)."""

from echotools.plat.capture.audio_record.config import AudioRecordConfig
from echotools.plat.capture.audio_record.win_wasapi import wasapi_record_name
from echotools.plat.capture.audio_record.win_winmm import winmm_record_name


def win_record_session(cfg: AudioRecordConfig) -> list[bytes]:
    names = cfg.device_names if cfg.device_names else ["default"]
    streams: list[bytes] = []
    for name in names:
        print(f"[*] Windows 开始录制设备: '{name}'  ({cfg.record_seconds}s)")
        try:
            pcm = wasapi_record_name(name, cfg)
            streams.append(pcm)
            print(f"[+] WASAPI 录制完成: '{name}'  {len(pcm)} bytes")
        except Exception as exc:
            print(f"[!] WASAPI 失败: {exc}\n    => 回退 winmm")
            try:
                pcm = winmm_record_name(name, cfg)
                streams.append(pcm)
                print(f"[+] winmm 录制完成: '{name}'  {len(pcm)} bytes")
            except Exception as exc2:
                raise RuntimeError(
                    f"Windows 设备 '{name}' 所有方案失败: {exc2}"
                ) from exc2
    return streams
