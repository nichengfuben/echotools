from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AudioMonitorConfig:
    """Configuration for audio session monitoring."""

    poll_interval_sec: float = 0.2
    print_on_change: bool = True
    show_timestamp: bool = True
    show_pid: bool = True
    active_state_only: bool = True
    banner_width: int = 60
