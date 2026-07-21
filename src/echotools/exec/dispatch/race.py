from __future__ import annotations

"""Concurrent candidate race helpers for TaskDispatcher."""

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from echotools.exec.dispatch.candidate import TaskCandidate

Executor = Callable[[TaskCandidate], Any]

RACE_CHUNK_TIMEOUT = 120.0


def new_race_info(idx: int, cand: TaskCandidate, q: asyncio.Queue, ev: asyncio.Event, task: asyncio.Task) -> Dict[str, Any]:
    return {
        "idx": idx,
        "cand": cand,
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
    }


def apply_queue_event(info: Dict[str, Any], tp: str, data: Any, min_tok: int) -> bool:
    """Apply one queue event; return True if this info becomes the winner."""
    if tp == "chunk":
        info["buf"].append(data)
        if isinstance(data, str):
            info["tok"] += 1
            info["ct"] += len(data) // 3
            if info["ft"] is None:
                info["ft"] = time.monotonic()
        elif isinstance(data, dict) and "usage" in data:
            info["ct"] = data["usage"].get("completion_tokens", info["ct"])
        return info["tok"] >= min_tok
    if tp == "done":
        info["done"] = True
    elif tp in ("err", "cancel"):
        info["err"] = True
        if data:
            info["err_msg"] = str(data)
    return False


async def race_worker(
    idx: int,
    cand: TaskCandidate,
    executor: Executor,
    q: asyncio.Queue,
    ev: asyncio.Event,
    wake: asyncio.Event,
) -> None:
    try:
        async for ch in executor(cand):
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
    except Exception as exc:
        try:
            await q.put(("err", idx, str(exc)))
            wake.set()
        except Exception:
            pass


def pick_fallback_winner(infos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    valid = [info for info in infos if info["buf"] and not info["err"]]
    if not valid:
        return None
    return max(valid, key=lambda x: x["tok"])


async def drain_winner(winner: Dict[str, Any]):
    """Yield remaining chunks from winner queue."""
    if winner["done"]:
        return
    while True:
        try:
            tp, _, data = await asyncio.wait_for(winner["q"].get(), RACE_CHUNK_TIMEOUT)
        except asyncio.TimeoutError:
            break
        if tp == "chunk":
            if isinstance(data, str):
                winner["tok"] += 1
                winner["ct"] += len(data) // 3
            elif isinstance(data, dict) and "usage" in data:
                winner["ct"] = data["usage"].get("completion_tokens", winner["ct"])
            yield data
        elif tp in ("done", "err", "cancel"):
            break


async def cancel_losers(infos: List[Dict[str, Any]], winner: Dict[str, Any], record_fn: Callable) -> None:
    for info in infos:
        if info is winner:
            continue
        info["ev"].set()
        if not info["task"].done():
            info["task"].cancel()
        await record_fn(info, info["tok"] > 0)
