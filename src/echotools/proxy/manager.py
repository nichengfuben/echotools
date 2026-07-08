from __future__ import annotations

"""代理管理器：环境变量/配置检测，HTTP/HTTPS/SOCKS 支持。

完全项目无关：代理服务器与启用开关由调用方传入或环境变量提供。
"""

import os
import re
import ssl
from typing import Any, Dict, List, Optional, Pattern

from echotools.logger.manager import get_logger

__all__ = ["ProxyManager"]

logger = get_logger(__name__)

_IP_RE = re.compile(r"^(https?://)?(\d{1,3}\.){3}\d{1,3}(:\d+)?(/|$)")
_LOCAL_HOSTS = re.compile(
    r"^(https?://)?(localhost|.*\.localhost)(:\d+)?(/|$)", re.IGNORECASE
)
_PROTOCOL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class ProxyManager:
    """代理管理器。

    支持环境变量与显式配置，提供 aiohttp connector 构造、
    URL 匹配判定，及 requests/aiohttp 的可选 monkeypatch。
    """

    def __init__(self) -> None:
        """初始化代理管理器。"""
        self._active = False
        self._proxies: Dict[str, str] = {}
        self._config_server = ""
        self._config_enabled = False
        self._patterns: List[Pattern[str]] = []

    def configure(
        self,
        proxy_server: str = "",
        enabled: bool = False,
        url_patterns: Optional[List[str]] = None,
    ) -> None:
        """配置代理。

        Args:
            proxy_server: 代理地址。
            enabled: 是否启用配置代理。
            url_patterns: URL 正则匹配列表，空表示全部非 IP 走代理。
        """
        self._config_server = proxy_server
        self._config_enabled = enabled
        self._patterns = [re.compile(p) for p in (url_patterns or [])]

    def activate(self) -> None:
        """激活代理（自动检测环境变量与配置）。"""
        self._proxies = self._resolve_proxies()
        self._proxies = {
            k: self._normalize(v) for k, v in self._proxies.items() if v
        }
        self._active = bool(self._proxies)
        if self._active:
            desc = ", ".join(
                "{}={}".format(k, v)
                for k, v in sorted(self._proxies.items())
            )
            logger.debug("代理已激活: %s", desc)
        else:
            logger.debug("代理未激活：无可用配置")

    def deactivate(self) -> None:
        """停用代理。"""
        self._active = False
        self._proxies = {}
        logger.debug("代理已停用")

    def is_active(self) -> bool:
        """返回是否激活。"""
        return self._active

    def get_proxy_dict(self) -> Dict[str, str]:
        """返回代理字典。"""
        return dict(self._proxies) if self._active else {}

    def should_proxy_url(self, url: str) -> bool:
        """判断 URL 是否应走代理。"""
        if not self._active or not self._proxies:
            return False
        if _IP_RE.match(url):
            return False
        if _LOCAL_HOSTS.match(url):
            return False
        if not self._patterns:
            return True
        return any(p.search(url) for p in self._patterns)

    def make_aiohttp_connector(
        self, proxy_url: Optional[str] = None
    ) -> Any:
        """为代理创建 aiohttp connector。

        Args:
            proxy_url: 代理 URL（SOCKS 使用专用 connector）。

        Returns:
            connector 实例。
        """
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        if proxy_url and self._is_socks(proxy_url):
            try:
                from aiohttp_socks import SocksConnector  # type: ignore[import]

                return SocksConnector(
                    socks_url=proxy_url,
                    ssl=ctx,
                    limit=200,
                    force_close=False,
                )
            except ImportError:
                logger.warning(
                    "aiohttp-socks 未安装，SOCKS 不可用: "
                    "pip install aiohttp-socks"
                )
        from aiohttp import TCPConnector  # type: ignore[import]

        return TCPConnector(ssl=ctx, limit=200, force_close=False)

    @staticmethod
    def _is_socks(url: str) -> bool:
        """判断是否 SOCKS 代理。"""
        return url.lower().startswith(
            ("socks5://", "socks5h://", "socks4://")
        )

    @staticmethod
    def _normalize(url: str) -> str:
        """规范化代理 URL。"""
        if not url:
            return url
        url = url.strip()
        if _PROTOCOL_RE.match(url):
            return url
        return "http://" + url

    def _resolve_proxies(self) -> Dict[str, str]:
        """解析最终代理（环境变量优先于配置）。"""
        env = self._detect_env()
        if env:
            return env
        if self._config_server and self._config_enabled:
            return {
                "http": self._config_server,
                "https": self._config_server,
            }
        return {}

    @staticmethod
    def _detect_env() -> Dict[str, str]:
        """检测环境变量代理。"""
        result: Dict[str, str] = {}
        http_proxy = (
            os.environ.get("HTTP_PROXY")
            or os.environ.get("http_proxy")
            or ""
        )
        if http_proxy:
            result["http"] = http_proxy
        https_proxy = (
            os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy")
            or ""
        )
        if https_proxy:
            result["https"] = https_proxy
        all_proxy = (
            os.environ.get("ALL_PROXY")
            or os.environ.get("all_proxy")
            or ""
        )
        if all_proxy:
            result.setdefault("http", all_proxy)
            result.setdefault("https", all_proxy)
        return result

    def patch_requests(self) -> None:
        """Monkey-patch requests 库以使用代理。"""
        try:
            import requests as _r  # type: ignore[import]

            _r.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            return

        mgr = self
        _orig = _r.Session.request

        def _patched_request(
            self: Any, method: str, url: str, *a: Any, **kw: Any
        ) -> Any:
            if not mgr.should_proxy_url(str(url)):
                return _orig(self, method, url, *a, **kw)
            if "proxies" not in kw:
                kw["proxies"] = mgr.get_proxy_dict()
                kw["verify"] = False
            return _orig(self, method, url, *a, **kw)

        _r.Session.request = _patched_request  # type: ignore[method-assign]

    def patch_aiohttp(self) -> None:
        """Monkey-patch aiohttp 以使用代理。

        支持 HTTP/HTTPS/SOCKS5 等协议。SOCKS 需要 aiohttp-socks 库。
        """
        try:
            from aiohttp import ClientSession  # type: ignore[import]
        except ImportError:
            return

        mgr = self
        _oi = ClientSession.__init__
        _or = ClientSession._request  # type: ignore[attr-defined]
        _oc = ClientSession.close

        def _pi(self: Any, *a: Any, **kw: Any) -> None:
            if "connector" not in kw:
                primary = None
                if mgr.is_active():
                    proxies = mgr.get_proxy_dict()
                    primary = proxies.get("https") or proxies.get("http")
                kw["connector"] = mgr.make_aiohttp_connector(primary)
            _oi(self, *a, **kw)
            self._proxy_dict = mgr.get_proxy_dict() if mgr.is_active() else {}
            self._has_socks = (
                mgr._is_socks(self._proxy_dict.get("https", ""))
                or mgr._is_socks(self._proxy_dict.get("http", ""))
            ) if mgr.is_active() else False

        async def _pr(self: Any, method: str, url: Any, **kw: Any) -> Any:
            if not mgr.should_proxy_url(str(url)):
                return await _or(self, method, url, **kw)
            if "proxy" not in kw and not getattr(self, "_has_socks", False):
                url_str = str(url)
                if url_str.startswith("https://"):
                    kw["proxy"] = self._proxy_dict.get("https") or self._proxy_dict.get("http")
                else:
                    kw["proxy"] = self._proxy_dict.get("http") or self._proxy_dict.get("https")
            return await _or(self, method, url, **kw)

        async def _pc(self: Any) -> None:
            try:
                await _oc(self)
            except Exception as e:
                logger.debug("aiohttp session 关闭异常: %s", e)

        ClientSession.__init__ = _pi  # type: ignore[method-assign]
        ClientSession._request = _pr  # type: ignore[attr-defined]
        ClientSession.close = _pc  # type: ignore[method-assign]

    def init(self) -> None:
        """初始化：patch requests/aiohttp 并激活代理。"""
        self.patch_requests()
        self.patch_aiohttp()
        self.activate()
