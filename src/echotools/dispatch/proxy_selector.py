"""Smart proxy selector: binary choice (proxy vs direct) with TAS-like scoring.

Tracks performance of proxy vs direct connections and uses a multi-dimensional
scoring algorithm to decide which path to use for each request.

Dimensions:
- n_fails: consecutive failure count (lower = better)
- last_success: timestamp of last success (more recent = better)
- ema_latency: EMA of response latency in ms (lower = better)
- n_calls: total call count (more data = more confident)

Persistence: separate JSON file (not the main usage.json).
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from echotools.logger.manager import get_logger

logger = get_logger(__name__)


@dataclass
class ProxyRecord:
    """Performance metrics for one connection path (proxy or direct)."""

    n_fails: int = 0
    last_success: float = 0.0
    ema_latency: float = 0.0
    n_calls: int = 0


class ProxySelector:
    """Binary proxy-vs-direct selector with exploration and TAS-like scoring.

    Usage::

        selector = ProxySelector(Path("persist/qwen/proxy.json"))
        use_proxy = selector.select()
        # ... make request ...
        selector.record(use_proxy, success=True, latency_ms=420.0)

    Scoring weights (4-dimensional, sum = 1.0):
    - fail_score:     0.30  (penalty for consecutive failures)
    - recency_score:  0.20  (bonus for recent success)
    - latency_score:  0.30  (lower EMA latency = better)
    - confidence:     0.20  (more calls = more confident)

    Exploration: 10% chance to try the less-used path, ensuring both
    paths are periodically tested.
    """

    _EXPLORATION_RATE: float = 0.10
    _MAX_FAIL_PENALTY: int = 10
    _RECENCY_HALFLIFE: float = 300.0  # 5 minutes
    _LATENCY_CEILING: float = 5000.0  # ms
    _CONFIDENCE_SATURATE: float = 50.0  # calls

    def __init__(self, persist_path: Path, ema_alpha: float = 0.3) -> None:
        self._path = persist_path
        self._alpha = ema_alpha
        self._proxy = ProxyRecord()
        self._direct = ProxyRecord()
        self._load()

    def select(self) -> bool:
        """Decide whether to use proxy (True) or direct (False).

        Considers both performance scoring and exploration.

        Returns:
            True to route through proxy, False for direct connection.
        """
        # --- exploration: ensure both paths have data ---
        if self._proxy.n_calls == 0 and self._direct.n_calls == 0:
            # Both untried: prefer proxy
            return True
        if self._proxy.n_calls == 0:
            return True
        if self._direct.n_calls == 0:
            return False

        # --- 10% exploration: randomly try the less-used path ---
        if random.random() < self._EXPLORATION_RATE:
            return self._proxy.n_calls < self._direct.n_calls

        # --- exploitation: score both and pick the better one ---
        proxy_score = self._score(self._proxy)
        direct_score = self._score(self._direct)
        return proxy_score >= direct_score

    def record(self, use_proxy: bool, success: bool, latency_ms: float = 0.0) -> None:
        """Record the outcome of a request.

        Args:
            use_proxy: Whether the request went through proxy.
            success: Whether the request succeeded.
            latency_ms: Response latency in milliseconds (only meaningful on success).
        """
        rec = self._proxy if use_proxy else self._direct
        if success:
            rec.n_fails = 0
            rec.last_success = time.time()
            rec.n_calls += 1
            if rec.ema_latency == 0:
                rec.ema_latency = latency_ms
            else:
                rec.ema_latency = (
                    self._alpha * latency_ms + (1 - self._alpha) * rec.ema_latency
                )
        else:
            rec.n_fails += 1
        self._save()

    # -------------------------------------------------------------------------
    # Scoring
    # -------------------------------------------------------------------------

    def _score(self, rec: ProxyRecord) -> float:
        """Compute composite score for a ProxyRecord.  Higher is better."""
        now = time.time()

        # Failure penalty: more consecutive fails → worse (range: -1.0 to 0.0)
        fail_score = -min(rec.n_fails, self._MAX_FAIL_PENALTY) / float(
            self._MAX_FAIL_PENALTY
        )

        # Recency bonus: more recent success → better (range: 0.0 to 1.0)
        if rec.last_success > 0:
            elapsed = now - rec.last_success
            recency = min(1.0, elapsed / self._RECENCY_HALFLIFE)
        else:
            recency = 1.0  # never succeeded → worst recency
        recency_score = 1.0 - recency

        # Latency score: lower EMA → better (range: 0.0 to 1.0)
        if rec.ema_latency > 0:
            lat_score = max(0.0, 1.0 - rec.ema_latency / self._LATENCY_CEILING)
        else:
            lat_score = 0.5  # no data → neutral

        # Confidence: more calls → more confident (range: 0.0 to 1.0)
        conf = min(1.0, rec.n_calls / self._CONFIDENCE_SATURATE)

        return (
            0.30 * fail_score
            + 0.20 * recency_score
            + 0.30 * lat_score
            + 0.20 * conf
        )

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Atomically persist proxy and direct records to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "proxy": asdict(self._proxy),
                "direct": asdict(self._direct),
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self._path))
        except Exception as e:
            logger.warning("ProxySelector 持久化写入失败: %s", e)

    def _load(self) -> None:
        """Load persisted records from disk (silent on missing/corrupt)."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if "proxy" in data:
                self._proxy = ProxyRecord(**data["proxy"])
            if "direct" in data:
                self._direct = ProxyRecord(**data["direct"])
        except Exception:
            pass
