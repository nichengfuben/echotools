from __future__ import annotations


class AudioProcess:
    __slots__ = ("pid", "name", "state", "volume")

    def __init__(
        self,
        pid: int,
        name: str,
        state: str = "active",
        volume: float = -1.0,
    ) -> None:
        self.pid = pid
        self.name = name
        self.state = state
        self.volume = volume

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AudioProcess):
            return NotImplemented
        return self.pid == other.pid and self.name == other.name

    def __hash__(self) -> int:
        return hash((self.pid, self.name))

    def __repr__(self) -> str:
        pid_s = f"PID={self.pid}" if self.pid else ""
        vol_s = f" vol={self.volume:.0%}" if self.volume >= 0 else ""
        parts = [p for p in (self.name, pid_s, vol_s) if p]
        return " | ".join(parts)
