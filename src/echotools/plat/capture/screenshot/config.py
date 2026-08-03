from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenshotConfig:
    """Configuration for multi-frame screenshot capture."""

    capture_count: int = 10
    output_dir: str = "screenshots"
    output_prefix: str = "frame"
    output_ext: str = "bmp"
    monitor_index: int = 0
    acquire_timeout_ms: int = 5000
    capture_interval_sec: float = 0.1
    bytes_per_pixel: int = 4
    draw_cursor: bool = True
    warmup_retries: int = 5

    def output_path(self, index: int, ext: str | None = None) -> str:
        import os

        use_ext = ext or self.output_ext
        return os.path.join(self.output_dir, f"{self.output_prefix}_{index:02d}.{use_ext}")
