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
from echotools.plat.capture.shared.bmp import rgba_to_bgra, write_bmp
from echotools.plat.capture.shared.pcm import clamp, mix_streams, resample_pcm
from echotools.plat.capture.shared.platform import (
    _OS,
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    load_lib,
)
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


def test_audio_process_eq_not_implemented() -> None:
    assert AudioProcess(1, "x").__eq__(None) is NotImplemented
    assert AudioProcess(0, "anon") == AudioProcess(0, "anon")
    assert "anon" in repr(AudioProcess(0, "anon"))


def test_mix_streams_empty() -> None:
    assert mix_streams([], 16) == b""


def test_mix_streams_single() -> None:
    data = b"\x00\x01\x00\x02"
    assert mix_streams([data], 16) == data


def test_mix_streams_pads_shorter_stream() -> None:
    s1 = struct.pack("<hh", 1000, 2000)
    s2 = struct.pack("<h", 3000)
    mixed = mix_streams([s1, s2], 16, mix_normalize=False)
    assert len(mixed) == len(s1)


def test_mix_streams_32bit() -> None:
    s1 = struct.pack("<ii", 1000, 2000)
    s2 = struct.pack("<ii", 3000, 4000)
    mixed = mix_streams([s1, s2], 32, mix_normalize=False)
    v1, v2 = struct.unpack("<ii", mixed)
    assert v1 == 2000
    assert v2 == 3000


def test_clamp() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(100, 0, 10) == 10


def test_resample_pcm_identity() -> None:
    pcm = struct.pack("<hh", 100, 200)
    assert resample_pcm(pcm, 44100, 2, 16, 44100, 2, 16) == pcm


def test_resample_pcm_mono_to_stereo() -> None:
    pcm = struct.pack("<h", 1000)
    out = resample_pcm(pcm, 44100, 1, 16, 44100, 2, 16)
    v1, v2 = struct.unpack("<hh", out)
    assert v1 == v2 == 1000


def test_resample_pcm_downsample() -> None:
    pcm = struct.pack("<hh", 100, 200) * 20
    out = resample_pcm(pcm, 44100, 2, 16, 22050, 2, 16)
    assert len(out) < len(pcm)


def test_resample_pcm_multi_channel() -> None:
    pcm = struct.pack("<hhhh", 1, 2, 3, 4)
    out = resample_pcm(pcm, 44100, 4, 16, 44100, 3, 16)
    assert len(out) == 6
    assert struct.unpack("<hhh", out) == (1, 2, 3)


def test_load_lib_missing() -> None:
    assert load_lib("echotools_nonexistent_lib_xyz") is None


def test_platform_flags() -> None:
    import platform

    assert _OS == platform.system()
    assert sum((IS_WINDOWS, IS_MACOS, IS_LINUX)) <= 1


def test_rgba_to_bgra() -> None:
    data = bytes([255, 0, 0, 255])
    out = rgba_to_bgra(data)
    assert out[0] == 0
    assert out[2] == 255


def test_write_bmp_bottom_up() -> None:
    pixels = b"\x00" * (4 * 2 * 2)
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "bottom.bmp")
        write_bmp(path, 2, 2, pixels, top_down=False)
        raw = Path(path).read_bytes()
    (height,) = struct.unpack_from("<i", raw, 22)
    assert height == 2


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
    assert cfg.total_frames == int(44100 * cfg.record_seconds)


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
