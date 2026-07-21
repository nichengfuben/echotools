from __future__ import annotations

"""通用 Web 应用工厂（aiohttp 适配，可选依赖）。"""

from typing import Any, List, Optional

from echotools.base.logger.manager import get_logger

__all__ = ["WebApplication"]

logger = get_logger(__name__)


class WebApplication:
    """通用 aiohttp Web 应用封装。

    提供 CORS、错误处理中间件与上下文存储，不绑定任何业务路由。
    """

    def __init__(
        self,
        *,
        client_max_size: int = 100 * 1024 * 1024,
        cors: bool = True,
        middlewares: Optional[List[Any]] = None,
    ) -> None:
        """初始化应用。

        Args:
            client_max_size: 请求体上限。
            cors: 是否启用 CORS。
            middlewares: 额外中间件。

        Raises:
            ImportError: aiohttp 未安装。
        """
        try:
            import aiohttp.web
        except ImportError as exc:
            raise ImportError(
                "WebApplication 需要 aiohttp: pip install aiohttp"
            ) from exc
        self._web = aiohttp.web
        mws: List[Any] = []
        if cors:
            mws.append(self._cors_middleware())
        mws.append(self._error_middleware())
        if middlewares:
            mws.extend(middlewares)
        self._app = aiohttp.web.Application(
            middlewares=mws, client_max_size=client_max_size
        )

    @property
    def app(self) -> Any:
        """底层 aiohttp Application。"""
        return self._app

    def __setitem__(self, key: Any, value: Any) -> None:
        self._app[key] = value

    def __getitem__(self, key: Any) -> Any:
        return self._app[key]

    def add_route(
        self, method: str, path: str, handler: Any
    ) -> None:
        """添加路由。"""
        self._app.router.add_route(method, path, handler)

    def _cors_middleware(self) -> Any:
        """构造 CORS 中间件。"""
        web = self._web

        @web.middleware
        async def _cors(request: Any, handler: Any) -> Any:
            if request.method == "OPTIONS":
                return web.Response(
                    status=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": (
                            "GET, POST, PUT, DELETE, OPTIONS, PATCH"
                        ),
                        "Access-Control-Allow-Headers": "*",
                        "Access-Control-Max-Age": "86400",
                    },
                )
            resp = await handler(request)
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            )
            resp.headers["Access-Control-Allow-Headers"] = "*"
            return resp

        return _cors

    def _error_middleware(self) -> Any:
        """构造错误处理中间件。"""
        web = self._web

        @web.middleware
        async def _err(request: Any, handler: Any) -> Any:
            try:
                return await handler(request)
            except web.HTTPException:
                raise
            except Exception as e:
                logger.error(
                    "未捕获异常 %s %s -> %s",
                    request.method,
                    request.path,
                    e,
                )
                return web.json_response(
                    {"error": {"message": str(e)}}, status=500
                )

        return _err
