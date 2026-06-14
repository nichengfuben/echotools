from __future__ import annotations

"""请求统计中间件 — 自动记录每次 API 请求的指标 + 请求日志广播。"""

import json
import time
import uuid
from typing import Callable, Optional

import aiohttp.web

from echotools.web.stats import RequestStats
from echotools.web.broker import RequestBroker

__all__ = ["create_stats_middleware"]


_DEFAULT_API_PREFIXES = ("/v1/chat/", "/v1/completions", "/v1/messages", "/v1/models", "/v1/embeddings")


def create_stats_middleware(
    stats: RequestStats,
    broker: RequestBroker,
    api_prefixes: tuple = _DEFAULT_API_PREFIXES,
):
    """创建请求统计中间件（依赖注入）。

    Args:
        stats: RequestStats 实例
        broker: RequestBroker 实例
        api_prefixes: 需要统计的 API 路径前缀
    """

    @aiohttp.web.middleware
    async def stats_middleware(
        request: aiohttp.web.Request,
        handler: Callable,
    ) -> aiohttp.web.StreamResponse:
        """记录 API 请求统计 + 广播请求事件。"""
        path = request.path

        if not any(path.startswith(p) for p in api_prefixes):
            return await handler(request)

        start = time.monotonic()
        status = 200
        platform = ""
        model = ""
        req_id = uuid.uuid4().hex[:16]
        body_info = {}

        try:
            if request.method == "POST" and request.content_type == "application/json":
                try:
                    body = await request.json()
                    model = body.get("model", "")
                    body_info = {
                        "model": model,
                        "messages_count": len(body.get("messages", [])),
                        "has_tools": bool(body.get("tools")),
                        "stream": bool(body.get("stream", False)),
                    }
                except Exception:
                    pass
        except Exception:
            pass

        # Broadcast request_start
        broker.push_event({
            "type": "request_start",
            "id": req_id,
            "ts": time.time(),
            **body_info,
        })

        try:
            response = await handler(request)
            status = response.status
            if hasattr(response, "_platform"):
                platform = response._platform

            # Wrap response.write to capture streaming chunks
            if hasattr(response, 'write') and body_info.get("stream"):
                original_write = response.write

                async def wrapped_write(data: bytes) -> None:
                    await original_write(data)
                    # Broadcast chunk (decode bytes to string, extract content from SSE)
                    try:
                        text = data.decode("utf-8", errors="replace")
                        # Extract content from SSE data lines
                        for line in text.split("\n"):
                            line = line.strip()
                            if line.startswith("data: ") and line != "data: [DONE]":
                                try:
                                    chunk = json.loads(line[6:])
                                    choices = chunk.get("choices", [])
                                    for choice in choices:
                                        delta = choice.get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            broker.push_event({
                                                "type": "request_chunk",
                                                "id": req_id,
                                                "delta": content,
                                            })
                                except Exception:
                                    pass
                    except Exception:
                        pass

                response.write = wrapped_write

            return response
        except aiohttp.web.HTTPException as exc:
            status = exc.status
            raise
        except Exception:
            status = 500
            raise
        finally:
            latency_ms = (time.monotonic() - start) * 1000
            stats.record(
                platform=platform,
                model=model,
                status=status,
                latency_ms=latency_ms,
            )
            # Broadcast request_end
            broker.push_event({
                "type": "request_end",
                "id": req_id,
                "status": status,
                "latency_ms": round(latency_ms, 1),
                "platform": platform,
                "model": model,
            })

    return stats_middleware
