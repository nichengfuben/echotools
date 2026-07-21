from __future__ import annotations

"""Request stats middleware with API metrics and request log broadcast."""

import time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple

from echotools.media.web.broker import RequestBroker
from echotools.media.web.stats import RequestStats
from echotools.media.web.stats import build_body_info, extract_response_text

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


async def _parse_request_body(request: "aiohttp_web.Request") -> tuple[str, Dict[str, Any]]:
    model = ""
    body_info: Dict[str, Any] = {}
    if request.content_type != "application/json":
        return model, body_info
    try:
        body = await request.json()
        model = body.get("model", "")
        body_info = build_body_info(body)
    except Exception:
        pass
    return model, body_info


def _capture_response_text(request: "aiohttp_web.Request", response: Any, body_info: Dict[str, Any]) -> None:
    if body_info.get("stream") or not hasattr(response, "body") or not response.body:
        return
    try:
        body_bytes = response.body if isinstance(response.body, bytes) else response.body.encode("utf-8")
        content = extract_response_text(body_bytes)
        if content:
            request["_req_log_chunks"].append(content)
    except Exception:
        pass


def _emit_request_end(
    broker: RequestBroker,
    stats: RequestStats,
    request: "aiohttp_web.Request",
    req_id: str,
    start: float,
    status: int,
    platform: str,
    model: str,
) -> None:
    latency_ms = (time.monotonic() - start) * 1000
    stats.record(platform=platform, model=model, status=status, latency_ms=latency_ms)
    chunks = request.get("_req_log_chunks", [])
    broker.push_event({
        "type": "request_end",
        "id": req_id,
        "status": status,
        "latency_ms": round(latency_ms, 1),
        "platform": platform,
        "model": model,
        "response": "".join(str(chunk) for chunk in chunks),
    })


def create_stats_middleware(
    stats: RequestStats,
    broker: RequestBroker,
    api_prefixes: Tuple[str, ...] = _DEFAULT_API_PREFIXES,
) -> Any:
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
        req_id = uuid.uuid4().hex[:16]
        model, body_info = await _parse_request_body(request)

        broker.push_event({"type": "request_start", "id": req_id, "ts": time.time(), **body_info})
        request["_req_log_id"] = req_id
        request["_req_log_chunks"] = []

        try:
            response = await handler(request)
            status = response.status
            if hasattr(response, "_platform"):
                platform = response._platform
            _capture_response_text(request, response, body_info)
            return response
        except aiohttp.web.HTTPException as exc:
            status = exc.status
            raise
        except Exception:
            status = 500
            raise
        finally:
            _emit_request_end(broker, stats, request, req_id, start, status, platform, model)

    return stats_middleware
