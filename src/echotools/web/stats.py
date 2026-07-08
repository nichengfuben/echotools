from __future__ import annotations

"""请求统计收集器 — 内存环形缓冲，零外部依赖。"""

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

__all__ = ["RequestStats", "get_stats"]


class _RingBuffer:
    """固定大小的环形缓冲。"""

    __slots__ = ("_buf", "_cap", "_idx", "_count")

    def __init__(self, capacity: int) -> None:
        self._buf: List[Dict[str, Any]] = []
        self._cap = capacity
        self._idx = 0
        self._count = 0

    def append(self, item: Dict[str, Any]) -> None:
        if self._count < self._cap:
            self._buf.append(item)
            self._count += 1
        else:
            self._buf[self._idx] = item
        self._idx = (self._idx + 1) % self._cap

    def snapshot(self) -> List[Dict[str, Any]]:
        if self._count < self._cap:
            return list(self._buf)
        return self._buf[self._idx:] + self._buf[:self._idx]

    def clear(self) -> None:
        self._buf.clear()
        self._idx = 0
        self._count = 0

    @property
    def count(self) -> int:
        return self._count


class RequestStats:
    """请求统计收集器。

    线程安全的内存统计，覆盖：
    - 请求计数（总计 / 按平台 / 按模型 / 按状态码）
    - 延迟分布（p50 / p95 / p99）
    - Token 用量（input / output）
    - 最近请求时间线（环形缓冲，用于 sparkline）
    """

    _MAX_TIMELINE = 1000
    _MAX_BUCKETS = 360
    _BUCKET_SECONDS = 10

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._errors = 0
        self._by_platform: Dict[str, int] = defaultdict(int)
        self._by_model: Dict[str, int] = defaultdict(int)
        self._by_status: Dict[int, int] = defaultdict(int)
        self._latencies: List[float] = []
        self._tokens_in = 0
        self._tokens_out = 0
        self._timeline = _RingBuffer(self._MAX_TIMELINE)
        self._time_buckets: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {"requests": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0}
        )
        self._start_time = time.time()

    def record(
        self,
        *,
        platform: str = "",
        model: str = "",
        status: int = 200,
        latency_ms: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """记录一次请求。"""
        is_error = status >= 400
        bucket_key = int(time.time()) // self._BUCKET_SECONDS

        with self._lock:
            self._total += 1
            if is_error:
                self._errors += 1
            if platform:
                self._by_platform[platform] += 1
            if model:
                self._by_model[model] += 1
            self._by_status[status] += 1
            if latency_ms > 0:
                self._latencies.append(latency_ms)
                if len(self._latencies) > 10000:
                    self._latencies = self._latencies[-5000:]
            self._tokens_in += tokens_in
            self._tokens_out += tokens_out

            self._timeline.append({
                "t": time.time(),
                "p": platform,
                "m": model,
                "s": status,
                "l": round(latency_ms, 1),
            })

            b = self._time_buckets[bucket_key]
            b["requests"] += 1
            if is_error:
                b["errors"] += 1
            b["tokens_in"] += tokens_in
            b["tokens_out"] += tokens_out

            if len(self._time_buckets) > self._MAX_BUCKETS:
                oldest = sorted(self._time_buckets)[:len(self._time_buckets) - self._MAX_BUCKETS]
                for k in oldest:
                    del self._time_buckets[k]

    def snapshot(self) -> Dict[str, Any]:
        """获取当前统计快照。"""
        with self._lock:
            uptime = time.time() - self._start_time
            rps = self._total / uptime if uptime > 0 else 0

            sorted_lat = sorted(self._latencies) if self._latencies else []
            n = len(sorted_lat)

            buckets = []
            for key in sorted(self._time_buckets):
                b = self._time_buckets[key]
                buckets.append({
                    "t": key * self._BUCKET_SECONDS,
                    "r": b["requests"],
                    "e": b["errors"],
                    "ti": b["tokens_in"],
                    "to": b["tokens_out"],
                })

            top_platforms = sorted(
                self._by_platform.items(), key=lambda x: x[1], reverse=True
            )[:10]
            top_models = sorted(
                self._by_model.items(), key=lambda x: x[1], reverse=True
            )[:10]

            return {
                "total": self._total,
                "errors": self._errors,
                "error_rate": round(self._errors / self._total * 100, 2) if self._total else 0,
                "rps": round(rps, 2),
                "uptime_seconds": round(uptime),
                "latency": {
                    "p50": round(sorted_lat[n // 2], 1) if n else 0,
                    "p95": round(sorted_lat[int(n * 0.95)], 1) if n else 0,
                    "p99": round(sorted_lat[int(n * 0.99)], 1) if n else 0,
                    "avg": round(sum(sorted_lat) / n, 1) if n else 0,
                },
                "tokens": {
                    "input": self._tokens_in,
                    "output": self._tokens_out,
                    "total": self._tokens_in + self._tokens_out,
                },
                "by_status": dict(self._by_status),
                "top_platforms": [{"name": k, "count": v} for k, v in top_platforms],
                "top_models": [{"name": k, "count": v} for k, v in top_models],
                "timeline": buckets,
                "recent": self._timeline.snapshot()[-50:],
            }

    def reset(self) -> None:
        """重置所有统计。"""
        with self._lock:
            self._total = 0
            self._errors = 0
            self._by_platform.clear()
            self._by_model.clear()
            self._by_status.clear()
            self._latencies.clear()
            self._tokens_in = 0
            self._tokens_out = 0
            self._timeline.clear()
            self._time_buckets.clear()
            self._start_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Export all stats data for persistence."""
        with self._lock:
            # Sample latencies to avoid huge payloads (keep last 1000)
            lat_sample = self._latencies[-1000:] if len(self._latencies) > 1000 else list(self._latencies)
            return {
                "total": self._total,
                "errors": self._errors,
                "by_platform": dict(self._by_platform),
                "by_model": dict(self._by_model),
                "by_status": {str(k): v for k, v in self._by_status.items()},
                "latencies": lat_sample,
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
                "timeline": self._timeline.snapshot(),
                "time_buckets": {str(k): v for k, v in self._time_buckets.items()},
                "start_time": self._start_time,
            }

    def restore(self, data: Dict[str, Any]) -> None:
        """Restore stats data from a persisted dict."""
        with self._lock:
            self._total = data.get("total", 0)
            self._errors = data.get("errors", 0)
            self._by_platform = defaultdict(int, data.get("by_platform", {}))
            self._by_model = defaultdict(int, data.get("by_model", {}))
            raw_status = data.get("by_status", {})
            self._by_status = defaultdict(int, {int(k): v for k, v in raw_status.items()})
            self._latencies = data.get("latencies", [])
            self._tokens_in = data.get("tokens_in", 0)
            self._tokens_out = data.get("tokens_out", 0)
            # Restore timeline ring buffer
            timeline_data = data.get("timeline", [])
            self._timeline.clear()
            for item in timeline_data:
                self._timeline.append(item)
            # Restore time buckets
            raw_buckets = data.get("time_buckets", {})
            self._time_buckets = defaultdict(
                lambda: {"requests": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0}
            )
            for k, v in raw_buckets.items():
                self._time_buckets[int(k)] = v
            # Restore start time for accurate uptime
            saved_start = data.get("start_time")
            if saved_start and isinstance(saved_start, (int, float)):
                self._start_time = saved_start


_instance: Optional[RequestStats] = None


def get_stats() -> RequestStats:
    """获取全局统计实例。"""
    global _instance
    if _instance is None:
        _instance = RequestStats()
    return _instance
