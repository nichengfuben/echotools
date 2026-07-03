"""贝叶斯代理选择器 -- 代理 vs 直连的汤普森采样。

将代理和直连视为两个臂，使用汤普森采样选择最优路径。
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from echotools.logger.manager import get_logger

logger = get_logger(__name__)


@dataclass
class ProxyRecord:
    """连接路径的贝叶斯充分统计量。"""

    n_success: int = 0
    n_fails: int = 0
    latency_sum: float = 0.0
    latency_sum_sq: float = 0.0
    n_latency_samples: int = 0
    last_success: float = 0.0
    last_used: float = 0.0
    n_calls: int = 0

    @property
    def success_rate(self) -> float:
        total = self.n_success + self.n_fails
        if total == 0:
            return 0.5
        return (self.n_success + 1) / (total + 2)

    @property
    def mean_latency(self) -> float:
        if self.n_latency_samples == 0:
            return 1000.0
        return self.latency_sum / self.n_latency_samples


class ProxySelector:
    """汤普森采样代理选择器。

    从 Beta 后验采样成功概率，从 Normal-InverseGamma 采样延迟，
    组合后选择奖励更高的路径。
    """

    _BETA_PRIOR_A: float = 2.0
    _BETA_PRIOR_B: float = 2.0
    _RECENCY_HALFLIFE: float = 300.0

    def __init__(self, persist_path: Path, ema_alpha: float = 0.3) -> None:
        self._path = persist_path
        self._alpha = ema_alpha
        self._proxy = ProxyRecord()
        self._direct = ProxyRecord()
        self._load()

    def select(self) -> bool:
        """汤普森采样决定是否使用代理。

        Returns:
            True 使用代理，False 直连。
        """
        now = time.time()
        proxy_reward = self._sample_reward(self._proxy, now)
        direct_reward = self._sample_reward(self._direct, now)

        logger.debug(
            "Thompson: proxy=%.4f, direct=%.4f",
            proxy_reward, direct_reward
        )
        return proxy_reward >= direct_reward

    def _sample_reward(self, r: ProxyRecord, now: float) -> float:
        """采样路径奖励。"""
        alpha = self._BETA_PRIOR_A + r.n_success
        beta = self._BETA_PRIOR_B + r.n_fails
        theta = np.random.beta(alpha, beta)

        latency = self._sample_latency(r)
        latency_reward = math.exp(-latency / 5000.0)

        if r.last_used == 0:
            recency = 1.5
        else:
            elapsed = now - r.last_used
            recency = 1.0 + 0.3 * (1.0 - math.exp(-elapsed / self._RECENCY_HALFLIFE))

        return theta * latency_reward * recency

    def _sample_latency(self, r: ProxyRecord) -> float:
        """采样延迟。"""
        if r.n_latency_samples < 2:
            return max(1.0, np.random.gamma(2, 500))
        
        n = r.n_latency_samples
        mean = r.latency_sum / n
        var = max(1.0, (r.latency_sum_sq / n) - mean**2)
        return max(1.0, np.random.normal(mean, math.sqrt(var / n)))

    def record(self, use_proxy: bool, success: bool, latency_ms: float = 0.0) -> None:
        """记录请求结果。"""
        r = self._proxy if use_proxy else self._direct
        now = time.time()
        r.last_used = now

        if success:
            r.n_success += 1
            r.n_calls += 1
            r.last_success = now
            if latency_ms > 0:
                r.latency_sum += latency_ms
                r.latency_sum_sq += latency_ms ** 2
                r.n_latency_samples += 1
        else:
            r.n_fails += 1

        self._save()

    def _save(self) -> None:
        """原子持久化。"""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "proxy": {
                    "n_success": self._proxy.n_success,
                    "n_fails": self._proxy.n_fails,
                    "latency_sum": self._proxy.latency_sum,
                    "latency_sum_sq": self._proxy.latency_sum_sq,
                    "n_latency_samples": self._proxy.n_latency_samples,
                    "last_success": self._proxy.last_success,
                    "last_used": self._proxy.last_used,
                    "n_calls": self._proxy.n_calls,
                },
                "direct": {
                    "n_success": self._direct.n_success,
                    "n_fails": self._direct.n_fails,
                    "latency_sum": self._direct.latency_sum,
                    "latency_sum_sq": self._direct.latency_sum_sq,
                    "n_latency_samples": self._direct.n_latency_samples,
                    "last_success": self._direct.last_success,
                    "last_used": self._direct.last_used,
                    "n_calls": self._direct.n_calls,
                },
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(self._path))
        except Exception as e:
            logger.warning("ProxySelector save failed: %s", e)

    def _load(self) -> None:
        """加载持久化记录。"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for key in ("proxy", "direct"):
                if key in data:
                    rec = ProxyRecord(**data[key])
                    setattr(self, f"_{key}", rec)
        except Exception:
            pass
