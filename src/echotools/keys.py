"""Generic key/account state management with rotation and failure tracking."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Generic, List, Optional, TypeVar

T = TypeVar('T')


@dataclass
class KeyState(Generic[T]):
    """Single key/account runtime state with failure tracking and cooldown.

    Generic over the key type ``T`` (typically ``str`` for API keys,
    but can be any credential object).

    Usage::

        ks = KeyState(key="sk-abc123")
        if ks.is_ready():
            try:
                result = call_api(ks.key)
                ks.mark_success()
            except Exception:
                ks.mark_failure(cooldown=120.0)
    """

    key: T
    available: bool = True
    n_fails: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    n_calls: int = 0
    cooldown_until: float = 0.0

    def mark_success(self) -> None:
        """Mark a successful call with this key."""
        self.available = True
        self.n_fails = 0
        self.last_success = time.time()
        self.n_calls += 1

    def mark_failure(self, cooldown: float = 60.0) -> None:
        """Mark a failed call.  After 3 consecutive failures the key enters cooldown.

        Args:
            cooldown: Cooldown duration in seconds once max failures reached.
        """
        self.n_fails += 1
        self.last_failure = time.time()
        if self.n_fails >= 3:
            self.available = False
            self.cooldown_until = time.time() + cooldown

    def is_ready(self) -> bool:
        """Check whether this key is available for use.

        Automatically recovers from cooldown once the cooldown period expires.
        """
        if self.available:
            return True
        if self.cooldown_until > 0 and time.time() > self.cooldown_until:
            self.available = True
            self.n_fails = 0
            return True
        return False


class KeyPool(Generic[T]):
    """Manages a pool of :class:`KeyState` instances for round-robin or best-key selection.

    Usage::

        pool = KeyPool(["sk-aaa", "sk-bbb", "sk-ccc"])
        best = pool.get_best()
        if best:
            try:
                result = call_api(best.key)
                best.mark_success()
            except Exception:
                best.mark_failure()
    """

    def __init__(self, keys: List[T]) -> None:
        self._states = [KeyState(key=k) for k in keys]

    def get_available(self) -> List[KeyState[T]]:
        """Return all keys that are currently ready for use."""
        return [s for s in self._states if s.is_ready()]

    def get_best(self) -> Optional[KeyState[T]]:
        """Return the available key with the fewest consecutive failures."""
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda s: s.n_fails)

    @property
    def available_count(self) -> int:
        """Number of currently available keys."""
        return len(self.get_available())

    @property
    def total_count(self) -> int:
        """Total number of keys in the pool."""
        return len(self._states)
