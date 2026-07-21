from __future__ import annotations

"""通用任务调度器：单发与并发竞速 -- 贝叶斯预筛选版。

竞速策略：
1. 使用汤普森采样预筛选候选（selector.select）
2. 对预筛选的候选启动并发竞速
3. 第一个达到 min_tokens 的候选成为胜者
4. 对胜者继续消费剩余流，对败者取消并记录部分成功
"""

import asyncio
import time
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

from echotools.base.errors.common import NoCandidateError
from echotools.base.logger.manager import get_logger
from echotools.exec.dispatch.candidate import TaskCandidate
from echotools.exec.dispatch.race import (
    apply_queue_event,
    cancel_losers,
    drain_winner,
    new_race_info,
    pick_fallback_winner,
    race_worker,
)
from echotools.exec.dispatch.selector import AdaptiveSelector

__all__ = ["TaskDispatcher"]

logger = get_logger(__name__)

_RACE_CHUNK_TIMEOUT = 120.0

Executor = Callable[
    [TaskCandidate], AsyncGenerator[Union[str, Dict[str, Any]], None]
]


class TaskDispatcher:
    """通用任务调度器。

    使用贝叶斯汤普森采样预筛选 + 并发竞速。
    """

    def __init__(self, selector: Optional[AdaptiveSelector] = None) -> None:
        self._selector = selector or AdaptiveSelector()

    @property
    def selector(self) -> AdaptiveSelector:
        return self._selector

    async def dispatch(
        self,
        candidates: List[TaskCandidate],
        executor: Executor,
        *,
        concurrent: int = 1,
        min_tokens: int = 10,
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """分发任务。

        流程：
        1. 汤普森采样预筛选 concurrent 个最优候选
        2. 若 concurrent=1：单候选执行
        3. 若 concurrent>1：并发竞速，首个达到 min_tokens 的胜出

        Args:
            candidates: 候选项列表。
            executor: 执行器回调。
            concurrent: 并发数（>1 启用竞速）。
            min_tokens: 竞速最小分片数。

        Yields:
            执行器产出的 str 或 dict。

        Raises:
            NoCandidateError: 无候选或全部失败。
        """
        if not candidates:
            raise NoCandidateError("No candidates")

        # 汤普森采样预筛选
        n = max(1, min(concurrent, len(candidates)))
        sel = await self._selector.select(candidates, n)

        if not sel:
            raise NoCandidateError("Selection returned empty")

        if len(sel) == 1:
            async for chunk in self._single(sel[0], executor):
                yield chunk
            return

        async for chunk in self._race(sel, executor, min_tokens):
            yield chunk

    async def _single(
        self, cand: TaskCandidate, executor: Executor
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """单候选执行。"""
        start = time.monotonic()
        ft: Optional[float] = None
        tc = 0
        ct = 0
        ok = False
        try:
            async for chunk in executor(cand):
                if isinstance(chunk, str):
                    tc += 1
                    ct += len(chunk) // 3  # 粗略估计 token
                    if ft is None:
                        ft = time.monotonic()
                elif isinstance(chunk, dict):
                    if "usage" in chunk:
                        u = chunk["usage"]
                        ct = u.get("completion_tokens", ct)
                yield chunk
            ok = True
        finally:
            dur = time.monotonic() - start
            lat = (ft - start) if ft else dur
            gen_dur = (time.monotonic() - ft) if ft else dur
            await self._selector.record(
                cand.id,
                ok,
                latency=lat,
                tokens=tc,
                duration=dur,
                generation_dur=gen_dur,
                completion_tokens=ct,
                group=cand.group,
            )

    async def _race(
        self,
        cands: List[TaskCandidate],
        executor: Executor,
        min_tok: int,
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """多候选并发竞速。"""
        infos: List[Dict[str, Any]] = []
        wake = asyncio.Event()
        for idx, c in enumerate(cands):
            q: "asyncio.Queue[Any]" = asyncio.Queue()
            ev = asyncio.Event()
            task = asyncio.ensure_future(race_worker(idx, c, executor, q, ev, wake))
            infos.append(new_race_info(idx, c, q, ev, task))

        winner: Optional[Dict[str, Any]] = None
        try:
            winner = await self._select_race_winner(infos, min_tok, wake)
            if winner is None:
                for info in infos:
                    await self._rec(info, False)
                raise NoCandidateError("All race candidates failed")

            await cancel_losers(infos, winner, self._rec)
            for ch in winner["buf"]:
                yield ch
            async for data in drain_winner(winner):
                yield data
            await self._rec(winner, True)
        except NoCandidateError:
            raise
        except Exception:
            for info in infos:
                info["ev"].set()
                if not info["task"].done():
                    info["task"].cancel()
            raise

    async def _select_race_winner(
        self,
        infos: List[Dict[str, Any]],
        min_tok: int,
        wake: asyncio.Event,
    ) -> Optional[Dict[str, Any]]:
        winner: Optional[Dict[str, Any]] = None
        while winner is None:
            if all(info["done"] or info["err"] for info in infos):
                break
            for info in infos:
                if info["done"] or info["err"]:
                    continue
                winner = self._poll_race_info(info, min_tok)
                if winner is not None:
                    break
            if winner is None:
                if all(info["done"] or info["err"] for info in infos):
                    break
                wake.clear()
                await wake.wait()
        return winner or pick_fallback_winner(infos)

    def _poll_race_info(
        self, info: Dict[str, Any], min_tok: int
    ) -> Optional[Dict[str, Any]]:
        while True:
            try:
                tp, _, data = info["q"].get_nowait()
            except asyncio.QueueEmpty:
                return None
            if apply_queue_event(info, tp, data, min_tok):
                return info
        return None

    async def _rec(self, info: Dict[str, Any], ok: bool) -> None:
        """记录竞速候选指标。"""
        try:
            dur = time.monotonic() - info["start"]
            lat = (info["ft"] - info["start"]) if info["ft"] else dur
            gen_dur = (time.monotonic() - info["ft"]) if info["ft"] else dur
            await self._selector.record(
                info["cand"].id,
                ok,
                latency=lat,
                tokens=info["tok"],
                duration=dur,
                generation_dur=gen_dur,
                completion_tokens=info["ct"],
                group=info["cand"].group,
            )
        except Exception as e:
            logger.warning("Record candidate [%s] failed: %s", info["cand"].id, e)
