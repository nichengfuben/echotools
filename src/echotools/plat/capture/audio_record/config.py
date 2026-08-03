from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioRecordConfig:
    """Configuration for multi-device audio recording."""

    device_names: list[str] = field(default_factory=lambda: ["default"])
    record_seconds: float = 5.0
    output_path: str = "output.wav"
    sample_rate: int = 44100
    channels: int = 2
    bit_depth: int = 16
    mix_normalize: bool = True
    buffer_ms: int = 50

    @property
    def bytes_per_sample(self) -> int:
        return self.bit_depth // 8

    @property
    def frame_bytes(self) -> int:
        return self.bytes_per_sample * self.channels

    @property
    def buffer_frames(self) -> int:
        return int(self.sample_rate * self.buffer_ms / 1000)

    @property
    def total_frames(self) -> int:
        return int(self.sample_rate * self.record_seconds)
