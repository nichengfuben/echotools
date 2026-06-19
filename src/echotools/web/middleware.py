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

        # Only capture POST requests (skip GET /v1/models etc.)
        if request.method != "POST":
            return await handler(request)

        start = time.monotonic()
        status = 200
        platform = ""
        model = ""
        req_id = uuid.uuid4().hex[:16]
        body_info = {}

        try:
            if request.content_type == "application/json":
                try:
                    body = await request.json()
                    model = body.get("model", "")
                    messages = body.get("messages", [])
                    # Truncate messages for display (keep first 500 chars per message)
                    display_messages = []
                    for msg in messages:
                        m = dict(msg)
                        content = m.get("content", "")
                        if isinstance(content, str) and len(content) > 500:
                            m["content"] = content[:500] + "...(truncated)"
                        elif isinstance(content, list):
                            m["content"] = str(content)[:500] + ("...(truncated)" if len(str(content)) > 500 else "")
                        display_messages.append(m)
                    body_info = {
                        "model": model,
                        "messages_count": len(messages),
                        "messages": display_messages,
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

        # Attach chunk collector to request for route handlers to push content
        request["_req_log_id"] = req_id
        request["_req_log_chunks"] = []

        try:
            response = await handler(request)
            status = response.status
            if hasattr(response, "_platform"):
                platform = response._platform

            # Non-streaming: capture response body
            if not body_info.get("stream") and hasattr(response, 'body') and response.body:
                try:
                    body_bytes = response.body if isinstance(response.body, bytes) else response.body.encode("utf-8")
                    text = body_bytes.decode("utf-8", errors="replace")
                    resp_data = json.loads(text)
                    choices = resp_data.get("choices", [])
                    content = ""
                    for choice in choices:
                        msg = choice.get("message", {})
                        content += msg.get("content", "")
                    if content:
                        request["_req_log_chunks"].append(content)
                except Exception:
                    pass

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
            # Broadcast collected chunks
            chunks = request.get("_req_log_chunks", [])
            for chunk_text in chunks:
                broker.push_event({
                    "type": "request_chunk",
                    "id": req_id,
                    "delta": chunk_text,
                })
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
