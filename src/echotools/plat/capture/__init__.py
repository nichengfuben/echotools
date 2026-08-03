from __future__ import annotations

"""Cross-platform audio/screenshot capture (ctypes + stdlib only)."""

from echotools.plat.capture.audio_monitor.api import (
    get_playing_processes,
    run_audio_monitor,
)
from echotools.plat.capture.audio_monitor.config import AudioMonitorConfig
from echotools.plat.capture.audio_monitor.types import AudioProcess
from echotools.plat.capture.audio_record.api import record_audio_session
from echotools.plat.capture.audio_record.config import AudioRecordConfig
from echotools.plat.capture.screenshot.api import capture_screenshots
from echotools.plat.capture.screenshot.config import ScreenshotConfig

__all__ = [
    "AudioMonitorConfig",
    "AudioProcess",
    "AudioRecordConfig",
    "ScreenshotConfig",
    "capture_screenshots",
    "get_playing_processes",
    "record_audio_session",
    "run_audio_monitor",
]
