from __future__ import annotations

"""Web 通用工具：JSON 响应、协议清理、安全 flush。"""

import json
from typing import Any, Optional, Tuple

__all__ = [
    "json_body",
    "json_response",
    "cors_middleware",
    "error_middleware",
    "safe_flush",
    "clean_fncall",
]


def json_body(data: Any, ensure_ascii: bool = False) -> bytes:
    """序列化为 JSON 字节。

    Args:
        data: 数据。
        ensure_ascii: 是否转义非 ASCII。

    Returns:
        UTF-8 编码的字节。
    """
    return json.dumps(data, ensure_ascii=ensure_ascii).encode("utf-8")


def json_response(
    data: Any,
    status: int = 200,
    headers: Optional[dict] = None,
) -> Any:
    """构造 JSON HTTP 响应（aiohttp 可选依赖）。

    Args:
        data: 将被序列化为 JSON 的数据。
        status: HTTP 状态码。
        headers: 额外响应头。

    Returns:
        aiohttp.web.Response 实例。

    Raises:
        ImportError: aiohttp 未安装。
    """
    try:
        import aiohttp.web
    except ImportError:
        raise ImportError("json_response 需要 aiohttp: pip install aiohttp")

    body = json.dumps(data, ensure_ascii=False)
    resp_headers = {"Content-Type": "application/json"}
    if headers:
        resp_headers.update(headers)
    return aiohttp.web.Response(
        body=body.encode("utf-8"),
        status=status,
        headers=resp_headers,
    )


def cors_middleware(
    allow_headers: str = "*",
    allow_methods: str = "GET, POST, PUT, DELETE, OPTIONS, PATCH",
) -> Any:
    """构造 CORS 中间件（aiohttp 可选依赖）。

    Args:
        allow_headers: Access-Control-Allow-Headers 值。
        allow_methods: Access-Control-Allow-Methods 值。

    Returns:
        aiohttp middleware 工厂。
    """
    import aiohttp.web

    @aiohttp.web.middleware
    async def _cors(request: Any, handler: Any) -> Any:
        if request.method == "OPTIONS":
            return aiohttp.web.Response(
                status=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": allow_methods,
                    "Access-Control-Allow-Headers": allow_headers,
                    "Access-Control-Max-Age": "86400",
                },
            )
        resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = allow_methods
        resp.headers["Access-Control-Allow-Headers"] = allow_headers
        return resp

    return _cors


def error_middleware(
    error_map: Optional[dict] = None,
) -> Any:
    """构造错误处理中间件（aiohttp 可选依赖）。

    Args:
        error_map: 异常类 → (status_code, error_type) 映射。
            例: {AuthError: (401, "authentication_error")}

    Returns:
        aiohttp middleware 工厂。
    """
    import aiohttp.web

    from echotools.logger.manager import get_logger

    _logger = get_logger(__name__)
    _emap = error_map or {}

    @aiohttp.web.middleware
    async def _err(request: Any, handler: Any) -> Any:
        try:
            return await handler(request)
        except aiohttp.web.HTTPException:
            raise
        except Exception as exc:
            for exc_type, (status, etype) in _emap.items():
                if isinstance(exc, exc_type):
                    return json_response(
                        {"error": {"message": str(exc), "type": etype}},
                        status=status,
                    )
            _logger.error(
                "未捕获异常: %s %s -> %s",
                request.method,
                request.path,
                exc,
            )
            return json_response(
                {"error": {"message": str(exc), "type": "server_error"}},
                status=500,
            )

    return _err


def clean_fncall(content: str, protocol: Any) -> str:
    """用协议清理 fncall 标签。

    Args:
        content: 原始文本。
        protocol: ToolProtocol 实例。

    Returns:
        清理后文本。
    """
    return protocol.clean_tags(content)


def safe_flush(
    buffer: str, protocol: Any
) -> Tuple[str, str]:
    """提取可安全输出前缀，保留潜在触发标记尾部。

    Args:
        buffer: 当前缓冲区。
        protocol: ToolProtocol 实例。

    Returns:
        (safe, remain)。
    """
    tags = protocol.get_trigger_tags()
    if not tags:
        return buffer, ""
    buf_len = len(buffer)
    max_keep = max(len(t) - 1 for t in tags)
    check_len = min(max_keep, buf_len)
    for length in range(check_len, 0, -1):
        suffix = buffer[buf_len - length :]
        if any(
            tag.startswith(suffix) and suffix != tag for tag in tags
        ):
            return (
                buffer[: buf_len - length],
                buffer[buf_len - length :],
            )
    return buffer, ""
