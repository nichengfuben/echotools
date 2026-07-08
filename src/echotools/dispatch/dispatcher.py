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

from echotools.dispatch.candidate import TaskCandidate
from echotools.dispatch.selector import AdaptiveSelector
from echotools.errors.common import NoCandidateError
from echotools.logger.manager import get_logger

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

        async def _worker(
            idx: int,
            c: TaskCandidate,
            q: "asyncio.Queue[Any]",
            ev: asyncio.Event,
            wake: asyncio.Event,
        ) -> None:
            try:
                async for ch in executor(c):
                    if ev.is_set():
                        break
                    await q.put(("chunk", idx, ch))
                    wake.set()
                await q.put(("done", idx, None))
                wake.set()
            except asyncio.CancelledError:
                try:
                    await q.put(("cancel", idx, None))
                    wake.set()
                except Exception:
                    pass
            except Exception as e:
                try:
                    await q.put(("err", idx, str(e)))
                    wake.set()
                except Exception:
                    pass

        wake = asyncio.Event()
        for idx, c in enumerate(cands):
            q: "asyncio.Queue[Any]" = asyncio.Queue()
            ev = asyncio.Event()
            task = asyncio.ensure_future(_worker(idx, c, q, ev, wake))
            infos.append({
                "idx": idx,
                "cand": c,
                "q": q,
                "ev": ev,
                "task": task,
                "tok": 0,
                "ct": 0,
                "buf": [],
                "start": time.monotonic(),
                "ft": None,
                "done": False,
                "err": False,
                "err_msg": "",
            })

        winner: Optional[Dict[str, Any]] = None
        try:
            while winner is None:
                if all(info["done"] or info["err"] for info in infos):
                    break
                for info in infos:
                    if info["done"] or info["err"]:
                        continue
                    while True:
                        try:
                            tp, _, data = info["q"].get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if tp == "chunk":
                            info["buf"].append(data)
                            if isinstance(data, str):
                                info["tok"] += 1
                                info["ct"] += len(data) // 3
                                if info["ft"] is None:
                                    info["ft"] = time.monotonic()
                            elif isinstance(data, dict) and "usage" in data:
                                info["ct"] = data["usage"].get(
                                    "completion_tokens", info["ct"]
                                )
                            if info["tok"] >= min_tok:
                                winner = info
                                break
                        elif tp == "done":
                            info["done"] = True
                        elif tp in ("err", "cancel"):
                            info["err"] = True
                            if data:
                                info["err_msg"] = str(data)
                    if winner is not None:
                        break
                if winner is None:
                    if all(info["done"] or info["err"] for info in infos):
                        break
                    wake.clear()
                    await wake.wait()

            # 无胜者：选择产出最多的
            if winner is None:
                valid = [info for info in infos if info["buf"] and not info["err"]]
                if valid:
                    winner = max(valid, key=lambda x: x["tok"])
                else:
                    for info in infos:
                        await self._rec(info, False)
                    raise NoCandidateError("All race candidates failed")

            # 取消败者，记录部分成功
            for info in infos:
                if info is not winner:
                    info["ev"].set()
                    if not info["task"].done():
                        info["task"].cancel()
                    await self._rec(info, info["tok"] > 0)

            # 产出胜者缓冲
            for ch in winner["buf"]:
                yield ch

            # 消费胜者剩余流
            if not winner["done"]:
                while True:
                    try:
                        tp, _, data = await asyncio.wait_for(
                            winner["q"].get(), _RACE_CHUNK_TIMEOUT
                        )
                        if tp == "chunk":
                            if isinstance(data, str):
                                winner["tok"] += 1
                                winner["ct"] += len(data) // 3
                            elif isinstance(data, dict) and "usage" in data:
                                winner["ct"] = data["usage"].get("completion_tokens", winner["ct"])
                            yield data
                        elif tp in ("done", "err", "cancel"):
                            break
                    except asyncio.TimeoutError:
                        logger.warning("Race queue timeout, ending early")
                        break

            await self._rec(winner, True)
        except NoCandidateError:
            raise
        except Exception:
            for info in infos:
                info["ev"].set()
                if not info["task"].done():
                    info["task"].cancel()
            raise

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
