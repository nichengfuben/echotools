from __future__ import annotations

"""通用任务调度器：单发与并发竞速。"""

import asyncio
import time
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
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

# 执行器签名：接收候选项，返回异步生成器（产出 str 或 dict）
Executor = Callable[
    [TaskCandidate], AsyncGenerator[Union[str, Dict[str, Any]], None]
]


class TaskDispatcher:
    """通用任务调度器。

    不绑定任何业务语义，通过 executor 回调执行实际任务，
    支持单候选执行与多候选并发竞速。
    """

    def __init__(self, selector: Optional[AdaptiveSelector] = None) -> None:
        """初始化调度器。

        Args:
            selector: 自适应选择器，None 时自动创建。
        """
        self._selector = selector or AdaptiveSelector()

    @property
    def selector(self) -> AdaptiveSelector:
        """选择器实例。"""
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

        Args:
            candidates: 候选项列表。
            executor: 执行器回调。
            concurrent: 并发数（>1 启用竞速）。
            min_tokens: 竞速最小分片数（决定胜者）。

        Yields:
            执行器产出的 str 或 dict。

        Raises:
            NoCandidateError: 无候选或选择失败。
        """
        if not candidates:
            raise NoCandidateError("无候选项")
        n = max(1, min(concurrent, len(candidates)))
        sel = await self._selector.select(candidates, n)
        if not sel:
            raise NoCandidateError("选择失败")
        if len(sel) == 1:
            async for chunk in self._single(sel[0], executor):
                yield chunk
            return
        async for chunk in self._race(sel, executor, min_tokens):
            yield chunk

    async def _single(
        self, cand: TaskCandidate, executor: Executor
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """单候选执行并记录指标。"""
        start = time.monotonic()
        ft: Optional[float] = None
        tc = 0
        ok = False
        try:
            async for chunk in executor(cand):
                if isinstance(chunk, str):
                    tc += 1
                    if ft is None:
                        ft = time.monotonic()
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
                group=cand.group,
            )

    async def _race(
        self,
        cands: List[TaskCandidate],
        executor: Executor,
        min_tok: int,
    ) -> AsyncGenerator[Union[str, Dict[str, Any]], None]:
        """多候选竞速执行。"""
        infos: List[Dict[str, Any]] = []

        async def _worker(
            idx: int,
            c: TaskCandidate,
            q: "asyncio.Queue[Any]",
            ev: asyncio.Event,
        ) -> None:
            try:
                async for ch in executor(c):
                    if ev.is_set():
                        break
                    await q.put(("chunk", idx, ch))
                await q.put(("done", idx, None))
            except asyncio.CancelledError:
                try:
                    await q.put(("cancel", idx, None))
                except Exception:
                    pass
            except Exception as e:
                try:
                    await q.put(("err", idx, str(e)))
                except Exception:
                    pass

        for i, c in enumerate(cands):
            q: "asyncio.Queue[Any]" = asyncio.Queue()
            ev = asyncio.Event()
            task = asyncio.ensure_future(_worker(i, c, q, ev))
            infos.append(
                {
                    "idx": i,
                    "cand": c,
                    "q": q,
                    "ev": ev,
                    "task": task,
                    "tok": 0,
                    "buf": [],
                    "start": time.monotonic(),
                    "ft": None,
                    "done": False,
                    "err": False,
                    "err_msg": "",
                }
            )

        winner: Optional[Dict[str, Any]] = None
        try:
            while winner is None:
                if all(i["done"] or i["err"] for i in infos):
                    break
                for info in infos:
                    if info["done"] or info["err"]:
                        continue
                    try:
                        tp, _, data = info["q"].get_nowait()
                    except asyncio.QueueEmpty:
                        continue
                    if tp == "chunk":
                        info["buf"].append(data)
                        if isinstance(data, str):
                            info["tok"] += 1
                            if info["ft"] is None:
                                info["ft"] = time.monotonic()
                        if info["tok"] >= min_tok:
                            winner = info
                            break
                    elif tp == "done":
                        info["done"] = True
                    elif tp in ("err", "cancel"):
                        info["err"] = True
                        if data:
                            info["err_msg"] = str(data)
                if winner is None:
                    await asyncio.sleep(0.02)

            if winner is None:
                valid = [i for i in infos if i["buf"] and not i["err"]]
                if valid:
                    winner = max(valid, key=lambda x: x["tok"])
                else:
                    for i in infos:
                        await self._rec(i, False)
                    raise NoCandidateError("所有并发任务失败")

            for i in infos:
                if i is not winner:
                    i["ev"].set()
                    if not i["task"].done():
                        i["task"].cancel()
                    await self._rec(i, i["tok"] > 0)

            for ch in winner["buf"]:
                yield ch

            if not winner["done"]:
                while True:
                    try:
                        tp, _, data = await asyncio.wait_for(
                            winner["q"].get(), _RACE_CHUNK_TIMEOUT
                        )
                        if tp == "chunk":
                            if isinstance(data, str):
                                winner["tok"] += 1
                            yield data
                        elif tp in ("done", "err", "cancel"):
                            break
                    except asyncio.TimeoutError:
                        logger.warning("竞速队列超时，提前结束")
                        break

            await self._rec(winner, True)
        except NoCandidateError:
            raise
        except Exception:
            for i in infos:
                i["ev"].set()
                if not i["task"].done():
                    i["task"].cancel()
            raise

    async def _rec(self, info: Dict[str, Any], ok: bool) -> None:
        """记录竞速候选指标。"""
        try:
            dur = time.monotonic() - info["start"]
            lat = (info["ft"] - info["start"]) if info["ft"] else dur
            gen_dur = (
                (time.monotonic() - info["ft"]) if info["ft"] else dur
            )
            await self._selector.record(
                info["cand"].id,
                ok,
                latency=lat,
                tokens=info["tok"],
                duration=dur,
                generation_dur=gen_dur,
                group=info["cand"].group,
            )
        except Exception as e:
            logger.warning(
                "记录候选 [%s] 失败: %s", info["cand"].id, e
            )
