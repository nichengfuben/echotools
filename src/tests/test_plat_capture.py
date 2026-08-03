from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

from echotools.plat.capture import (
    AudioMonitorConfig,
    AudioProcess,
    AudioRecordConfig,
    ScreenshotConfig,
    get_playing_processes,
)
from echotools.plat.capture.shared.bmp import write_bmp
from echotools.plat.capture.shared.pcm import mix_streams
from echotools.plat.capture.shared.wav import write_wav


def test_audio_process_equality() -> None:
    a = AudioProcess(1, "foo.exe", "active", 0.5)
    b = AudioProcess(1, "foo.exe", "inactive", -1.0)
    assert a == b
    assert hash(a) == hash(b)
    assert "foo.exe" in repr(a)
    assert "PID=1" in repr(a)
    assert "vol=50%" in repr(a)


def test_audio_process_unknown_volume() -> None:
    ap = AudioProcess(2, "bar", "unknown")
    assert ap.volume == -1.0
    assert "vol=" not in repr(ap)


def test_mix_streams_single() -> None:
    data = b"\x00\x01\x00\x02"
    assert mix_streams([data], 16) == data


def test_mix_streams_average() -> None:
    s1 = struct.pack("<hh", 1000, 2000)
    s2 = struct.pack("<hh", 3000, 4000)
    mixed = mix_streams([s1, s2], 16, mix_normalize=False)
    v1, v2 = struct.unpack("<hh", mixed)
    assert v1 == 2000
    assert v2 == 3000


def test_mix_streams_normalize() -> None:
    s1 = struct.pack("<h", 30000)
    s2 = struct.pack("<h", 30000)
    mixed = mix_streams([s1, s2], 16, mix_normalize=True)
    (v,) = struct.unpack("<h", mixed)
    assert v == 32767


def test_write_wav_roundtrip_header() -> None:
    pcm = struct.pack("<hhhh", 0, 100, -100, 200)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "test.wav")
        write_wav(path, pcm, 44100, 2, 16)
        raw = Path(path).read_bytes()
    assert raw[:4] == b"RIFF"
    assert raw[8:12] == b"WAVE"
    assert raw[12:16] == b"fmt "
    assert raw[36:40] == b"data"
    assert len(raw) == 44 + len(pcm)


def test_write_bmp_header() -> None:
    pixels = b"\x00" * (4 * 2 * 2)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "test.bmp")
        write_bmp(path, 2, 2, pixels, top_down=True)
        raw = Path(path).read_bytes()
    assert raw[:2] == b"BM"
    assert len(raw) == 54 + len(pixels)


def test_audio_monitor_config_defaults() -> None:
    cfg = AudioMonitorConfig()
    assert cfg.poll_interval_sec == 0.2
    assert cfg.print_on_change is True
    assert cfg.active_state_only is True
    assert cfg.banner_width == 60


def test_audio_record_config_defaults() -> None:
    cfg = AudioRecordConfig()
    assert cfg.device_names == ["default"]
    assert cfg.record_seconds == 5.0
    assert cfg.output_path == "output.wav"
    assert cfg.sample_rate == 44100
    assert cfg.channels == 2
    assert cfg.bit_depth == 16
    assert cfg.mix_normalize is True
    assert cfg.buffer_ms == 50
    assert cfg.frame_bytes == 4
    assert cfg.buffer_frames == int(44100 * 50 / 1000)


def test_screenshot_config_defaults() -> None:
    cfg = ScreenshotConfig()
    assert cfg.capture_count == 10
    assert cfg.output_dir == "screenshots"
    assert cfg.output_prefix == "frame"
    assert cfg.output_ext == "bmp"
    assert cfg.monitor_index == 0
    assert cfg.acquire_timeout_ms == 5000
    assert cfg.capture_interval_sec == 0.1
    assert cfg.draw_cursor is True
    assert cfg.warmup_retries == 5


def test_screenshot_config_output_path() -> None:
    cfg = ScreenshotConfig(output_dir="out", output_prefix="snap")
    assert cfg.output_path(3) == os.path.join("out", "snap_03.bmp")
    assert cfg.output_path(3, "png") == os.path.join("out", "snap_03.png")


def test_get_playing_processes_returns_list() -> None:
    result = get_playing_processes()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, AudioProcess)
