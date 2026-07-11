from __future__ import annotations

"""Request stats middleware with API metrics and request log broadcast."""

import json
import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple

from echotools.web.broker import RequestBroker
from echotools.web.stats import RequestStats

if TYPE_CHECKING:
    from aiohttp import web as aiohttp_web

__all__ = ["create_stats_middleware"]

_DEFAULT_API_PREFIXES = (
    "/v1/chat/",
    "/v1/completions",
    "/v1/messages",
    "/v1/models",
    "/v1/embeddings",
)


def create_stats_middleware(
    stats: RequestStats,
    broker: RequestBroker,
    api_prefixes: Tuple[str, ...] = _DEFAULT_API_PREFIXES,
) -> Any:
    """Create request stats middleware (dependency injection).

    Args:
        stats: RequestStats instance.
        broker: RequestBroker instance.
        api_prefixes: API path prefixes to track.

    Raises:
        ImportError: aiohttp is not installed.
    """
    try:
        import aiohttp.web
    except ImportError as exc:
        raise ImportError(
            "create_stats_middleware requires aiohttp: pip install echotools[http]"
        ) from exc

    @aiohttp.web.middleware
    async def stats_middleware(
        request: "aiohttp_web.Request",
        handler: Callable,
    ) -> "aiohttp_web.StreamResponse":
        path = request.path

        if not any(path.startswith(p) for p in api_prefixes):
            return await handler(request)

        if request.method != "POST":
            return await handler(request)

        start = time.monotonic()
        status = 200
        platform = ""
        model = ""
        req_id = uuid.uuid4().hex[:16]
        body_info: Dict[str, Any] = {}

        try:
            if request.content_type == "application/json":
                try:
                    body = await request.json()
                    model = body.get("model", "")
                    messages = body.get("messages", [])
                    display_messages = []
                    for msg in messages:
                        m = dict(msg)
                        content = m.get("content", "")
                        if isinstance(content, str) and len(content) > 500:
                            m["content"] = content[:500] + "...(truncated)"
                        elif isinstance(content, list):
                            text = str(content)
                            m["content"] = text[:500] + (
                                "...(truncated)" if len(text) > 500 else ""
                            )
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

        broker.push_event({
            "type": "request_start",
            "id": req_id,
            "ts": time.time(),
            **body_info,
        })

        request["_req_log_id"] = req_id
        request["_req_log_chunks"] = []

        try:
            response = await handler(request)
            status = response.status
            if hasattr(response, "_platform"):
                platform = response._platform

            if not body_info.get("stream") and hasattr(response, "body") and response.body:
                try:
                    body_bytes = (
                        response.body
                        if isinstance(response.body, bytes)
                        else response.body.encode("utf-8")
                    )
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
            chunks = request.get("_req_log_chunks", [])
            response_text = "".join(str(chunk) for chunk in chunks)
            broker.push_event({
                "type": "request_end",
                "id": req_id,
                "status": status,
                "latency_ms": round(latency_ms, 1),
                "platform": platform,
                "model": model,
                "response": response_text,
            })

    return stats_middleware
