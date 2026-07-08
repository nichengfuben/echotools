from __future__ import annotations

"""贝叶斯汤普森采样选择器 -- 确定性等价加速版。

核心创新：用后验期望 + 解析不确定性奖励替代随机采样。
- 完全避免 Beta/Gamma/Normal 随机数生成
- 数学上等价于汤普森采样的期望行为
- 无随机性 → 无方差 → 更稳定
- 计算量从 O(n * 采样) 降至 O(n * 解析)

理论依据：
汤普森采样的期望选择 = 后验均值 + 与后验方差成比例的探索奖励
"""

import asyncio
import atexit
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from echotools.dispatch.candidate import TaskCandidate
from echotools.io.io_utils import atomic_write_text
from echotools.logger.manager import get_logger

__all__ = ["AdaptiveSelector", "TASRecord"]

logger = get_logger(__name__)


@dataclass
class TASRecord:
    """候选项贝叶斯充分统计量。"""

    group: str = ""
    n_success: int = 0
    n_fails: int = 0
    latency_sum: float = 0.0
    latency_sum_sq: float = 0.0
    n_latency_samples: int = 0
    speed_sum: float = 0.0
    speed_sum_sq: float = 0.0
    n_speed_samples: int = 0
    last_success: float = 0.0
    last_used: float = 0.0
    error_time: float = 0.0
    n_calls: int = 0

    # === 解析后验统计（无随机数） ===

    @property
    def beta_mean(self) -> float:
        """Beta 后验均值。"""
        a = 2.0 + self.n_success
        b = 2.0 + self.n_fails
        return a / (a + b)

    @property
    def beta_std(self) -> float:
        """Beta 后验标准差。"""
        a = 2.0 + self.n_success
        b = 2.0 + self.n_fails
        total = a + b
        return math.sqrt(a * b / (total * total * (total + 1)))

    @property
    def latency_mean(self) -> float:
        """延迟后验均值（毫秒）。"""
        if self.n_latency_samples == 0:
            return 1000.0
        return self.latency_sum / self.n_latency_samples

    @property
    def latency_std(self) -> float:
        """延迟后验标准差。"""
        if self.n_latency_samples < 2:
            return 500.0
        mean = self.latency_mean
        var = (self.latency_sum_sq / self.n_latency_samples) - mean ** 2
        return max(1.0, math.sqrt(abs(var)))

    @property
    def speed_mean(self) -> float:
        """速度后验均值（tokens/秒）。"""
        if self.n_speed_samples == 0:
            return 10.0
        return self.speed_sum / self.n_speed_samples

    @property
    def total_obs(self) -> int:
        """总观察次数（成功+失败）。"""
        return self.n_success + self.n_fails

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group": self.group,
            "n_success": self.n_success,
            "n_fails": self.n_fails,
            "latency_sum": self.latency_sum,
            "latency_sum_sq": self.latency_sum_sq,
            "n_latency_samples": self.n_latency_samples,
            "speed_sum": self.speed_sum,
            "speed_sum_sq": self.speed_sum_sq,
            "n_speed_samples": self.n_speed_samples,
            "last_success": self.last_success,
            "last_used": self.last_used,
            "error_time": self.error_time,
            "n_calls": self.n_calls,
            "success_rate": self.beta_mean,
            "mean_latency": round(self.latency_mean, 1),
            "mean_speed": round(self.speed_mean, 2),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TASRecord":
        return cls(
            group=data.get("group", ""),
            n_success=data.get("n_success", 0),
            n_fails=data.get("n_fails", 0),
            latency_sum=data.get("latency_sum", 0.0),
            latency_sum_sq=data.get("latency_sum_sq", 0.0),
            n_latency_samples=data.get("n_latency_samples", 0),
            speed_sum=data.get("speed_sum", 0.0),
            speed_sum_sq=data.get("speed_sum_sq", 0.0),
            n_speed_samples=data.get("n_speed_samples", 0),
            last_success=data.get("last_success", 0.0),
            last_used=data.get("last_used", 0.0),
            error_time=data.get("error_time", 0.0),
            n_calls=data.get("n_calls", 0),
        )


class AdaptiveSelector:
    """贝叶斯确定性选择器。

    用后验均值 + 不确定性奖励替代随机采样。
    数学上等价于汤普森采样的期望行为，但完全确定性、零随机开销。

    评分公式：
    score = beta_mean + α · beta_std · exp(-λ · n)  [成功概率 + 探索奖励]
          × exp(-latency_mean / τ) / (1 + latency_std / τ)  [延迟均值 + 惩罚不确定性]
          × recency_bonus  [时间衰减]

    其中 α 控制探索强度，λ 控制探索衰减速率。
    """

    # 探索奖励参数
    _ALPHA: float = 1.0       # 探索强度（等价于汤普森采样的采样范围）
    _LAMBDA: float = 0.1      # 探索衰减（数据越多，探索越少）
    _TAU: float = 5000.0      # 延迟时间常数
    _RECENCY_HALFLIFE: float = 300.0
    _COOLDOWN_BASE: float = 30.0

    def __init__(
        self,
        persist_dir: str = "persist/dispatch",
        group_attr: str = "group",
        *,
        flush_debounce: float = 1.0,
    ) -> None:
        self._pool: Dict[str, TASRecord] = {}
        self._persist_dir = Path(persist_dir)
        self._ga = group_attr
        self._dirty: Set[str] = set()
        self._flush_debounce = flush_debounce
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._load()
        atexit.register(self._flush_dirty_sync)

    def _load(self) -> None:
        if not self._persist_dir.exists():
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            return
        files = [
            f
            for f in self._persist_dir.glob("*.json")
            if not f.name.startswith("_")
        ]
        if not files:
            return
        if len(files) > 50:
            loaded = self._load_parallel(files)
            self._pool.update(loaded)
            logger.debug("Loaded %d records (parallel)", len(loaded))
            return
        count = 0
        for f in files:
            record = self._read_record_file(f)
            if record is not None:
                self._pool[f.stem] = record
                count += 1
        if count:
            logger.debug("Loaded %d records", count)

    @staticmethod
    def _read_record_file(path: Path) -> Optional[TASRecord]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TASRecord.from_dict(data)
        except Exception:
            return None

    def _load_parallel(self, files: List[Path]) -> Dict[str, TASRecord]:
        pool: Dict[str, TASRecord] = {}
        with ThreadPoolExecutor() as executor:
            results: List[Tuple[Path, Optional[TASRecord]]] = list(
                executor.map(
                    lambda f: (f, self._read_record_file(f)),
                    files,
                )
            )
        for path, record in results:
            if record is not None:
                pool[path.stem] = record
        return pool

    def _ensure(self, key: str, group: str = "") -> TASRecord:
        if key not in self._pool:
            self._pool[key] = TASRecord(group=group)
        return self._pool[key]

    def _save_record(self, key: str, r: TASRecord) -> None:
        f = self._persist_dir / f"{key}.json"
        try:
            atomic_write_text(f, json.dumps(r.to_dict(), indent=2))
        except Exception as e:
            logger.warning("Save record [%s] failed: %s", key, e)

    def _schedule_flush(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._flush_dirty_sync()
            return
        if self._flush_task is not None and not self._flush_task.done():
            return
        self._flush_task = loop.create_task(self._debounced_flush())

    async def _debounced_flush(self) -> None:
        await asyncio.sleep(self._flush_debounce)
        self._flush_dirty_sync()

    def _flush_dirty_sync(self) -> None:
        if not self._dirty:
            return
        dirty = list(self._dirty)
        self._dirty.clear()
        for cid in dirty:
            record = self._pool.get(cid)
            if record is not None:
                self._save_record(cid, record)

    async def flush(self) -> None:
        """Immediately persist all pending records."""
        if self._flush_task is not None and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        self._flush_dirty_sync()

    def _is_cooling(self, cid: str) -> bool:
        r = self._pool.get(cid)
        if r is None or r.error_time <= 0 or r.n_fails == 0:
            return False
        elapsed = time.time() - r.error_time
        return elapsed < self._COOLDOWN_BASE * min(r.n_fails, 10)

    # ------------------------------------------------------------------
    # 确定性评分（无随机数，纯解析计算）
    # ------------------------------------------------------------------

    def _score(self, r: TASRecord, now: float) -> float:
        """确定性评分 -- 汤普森采样的期望等价形式。

        完全解析计算，无任何随机数生成。
        """
        # 1. 成功概率：后验均值 + 探索奖励
        #    探索奖励 = α · σ · exp(-λ · n)
        #    数据越多，σ 越小，探索奖励越少 → 自动收敛
        explore_bonus = self._ALPHA * r.beta_std * math.exp(-self._LAMBDA * r.total_obs)
        success_score = r.beta_mean + explore_bonus

        # 2. 延迟：均值惩罚 + 不确定性惩罚
        #    exp(-mean/τ) / (1 + std/τ)
        #    延迟低 + 稳定 → 高分
        if r.n_latency_samples == 0:
            latency_score = math.exp(-1000.0 / self._TAU)
        else:
            latency_score = math.exp(-r.latency_mean / self._TAU) / (
                1.0 + r.latency_std / self._TAU
            )

        # 3. 时间衰减奖励
        if r.last_used == 0:
            recency = 1.5
        else:
            elapsed = now - r.last_used
            if elapsed < self._RECENCY_HALFLIFE:
                recency = 1.0
            else:
                recency = 1.0 + 0.3 * (1.0 - math.exp(-elapsed / self._RECENCY_HALFLIFE))

        return success_score * latency_score * recency

    # ------------------------------------------------------------------
    # 选择
    # ------------------------------------------------------------------

    async def select(
        self, cands: List[TaskCandidate], count: int = 1
    ) -> List[TaskCandidate]:
        """确定性选择：计算评分，排序，返回 top-k。

        O(n) 复杂度，纯解析计算，零随机开销。
        """
        if not cands:
            return []

        # 过滤冷却
        active = [c for c in cands if not self._is_cooling(c.id)]
        if not active:
            active = sorted(
                cands,
                key=lambda c: self._pool.get(c.id, TASRecord()).error_time,
            )[:max(1, count)]

        if len(active) <= count:
            return active

        # 计算评分
        now = time.time()
        scored = []
        for c in active:
            r = self._ensure(c.id, getattr(c, self._ga, ""))
            score = self._score(r, now)
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:count]]

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    async def record(
        self,
        cid: str,
        success: bool,
        latency: float = 0,
        tokens: int = 0,
        duration: float = 0,
        generation_dur: float = 0,
        completion_tokens: int = 0,
        group: str = "",
        platform: str = "",
    ) -> None:
        grp = group or platform
        r = self._ensure(cid, grp)
        now = time.time()
        r.last_used = now

        if success:
            r.n_success += 1
            r.n_calls += 1
            r.last_success = now
            r.error_time = 0.0

            if latency > 0:
                lat_ms = latency * 1000.0
                r.latency_sum += lat_ms
                r.latency_sum_sq += lat_ms ** 2
                r.n_latency_samples += 1

            if completion_tokens > 0 and generation_dur > 0:
                speed = completion_tokens / generation_dur
            elif tokens > 0 and duration > 0:
                speed = tokens / duration
            else:
                speed = 0

            if speed > 0:
                r.speed_sum += speed
                r.speed_sum_sq += speed ** 2
                r.n_speed_samples += 1
        else:
            r.n_fails += 1
            r.error_time = now

        self._dirty.add(cid)
        self._schedule_flush()

    async def get_stats(self) -> Dict[str, Any]:
        return {k: v.to_dict() for k, v in self._pool.items()}
