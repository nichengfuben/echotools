from __future__ import annotations

"""异步重试工具。"""

import asyncio
from typing import Any, AsyncGenerator, Callable, Optional, Tuple, Type, TypeVar

from echotools.logger.manager import get_logger

__all__ = ["retry_with_backoff", "retry_on_empty", "retry_on_exception", "retry_async_generator"]

logger = get_logger(__name__)


async def retry_with_backoff(
    func: Callable[..., Any],
    *a: Any,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kw: Any,
) -> Any:
    """指数退避重试。

    Args:
        func: 异步可调用对象。
        max_attempts: 最大尝试次数。
        base_delay: 初始等待秒数。
        max_delay: 最大等待秒数。
        exceptions: 需重试的异常类型。

    Returns:
        函数执行结果。

    Raises:
        最后一次异常。
    """
    last: Optional[Exception] = None
    for i in range(max_attempts):
        try:
            return await func(*a, **kw)
        except exceptions as e:
            last = e
            if i < max_attempts - 1:
                d = min(base_delay * (2 ** i), max_delay)
                logger.warning(
                    "重试 %d/%d: %s，%.1fs 后重试",
                    i + 1,
                    max_attempts,
                    e,
                    d,
                )
                await asyncio.sleep(d)
    raise last  # type: ignore[misc]


async def retry_on_empty(
    func: Callable[..., Any],
    *a: Any,
    max_retries: int = 3,
    **kw: Any,
) -> Any:
    """空响应重试。

    Args:
        func: 异步可调用对象。
        max_retries: 最大重试次数。

    Returns:
        非空结果。

    Raises:
        ValueError: 仍为空。
    """
    for i in range(max_retries):
        try:
            r = await func(*a, **kw)
            if r is None:
                raise ValueError("None response")
            if isinstance(r, str) and not r.strip():
                raise ValueError("empty string response")
            if isinstance(r, dict):
                c = r.get("text", r.get("content", ""))
                if isinstance(c, str) and not c.strip():
                    raise ValueError("empty content")
            return r
        except ValueError:
            if i < max_retries - 1:
                await asyncio.sleep(1.0 * (2 ** i))
            else:
                raise


async def retry_on_exception(
    func: Callable[..., Any],
    *a: Any,
    max_retries: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kw: Any,
) -> Any:
    """指定异常类型重试。

    Args:
        func: 异步可调用对象。
        max_retries: 最大重试次数。
        exceptions: 触发重试的异常类型。
        on_retry: 重试回调(attempt, error)。

    Returns:
        函数执行结果。

    Raises:
        最后一次异常。
    """
    last: Optional[Exception] = None
    for i in range(max_retries):
        try:
            return await func(*a, **kw)
        except exceptions as e:
            last = e
            if on_retry is not None:
                on_retry(i + 1, e)
            if i < max_retries - 1:
                await asyncio.sleep(1.0 * (2 ** i))
    raise last  # type: ignore[misc]


async def retry_async_generator(
    gen_factory: Callable[..., AsyncGenerator[Any, None]],
    *a: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    fatal_check: Optional[Callable[[Exception], bool]] = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kw: Any,
) -> AsyncGenerator[Any, None]:
    """Retry an async generator factory with exponential backoff.

    On each retry the generator is re-created from scratch via *gen_factory*.
    This is the standard pattern used across platform clients where each
    ``async for chunk in self._do_request(...)`` call is a fresh HTTP request.

    Args:
        gen_factory: Callable that returns an async generator.
        *a: Positional arguments forwarded to *gen_factory*.
        max_retries: Maximum number of retry attempts (0 = no retries).
        base_delay: Initial backoff delay in seconds.
        max_delay: Maximum backoff delay cap in seconds.
        fatal_check: Optional callable ``(exc) -> bool``.  Return ``True``
            to treat the exception as fatal and skip retrying (e.g. auth
            errors or quota exhaustion).
        exceptions: Exception types that trigger a retry.
        **kw: Keyword arguments forwarded to *gen_factory*.

    Yields:
        Items from the successful generator invocation.

    Raises:
        The last exception if all retries are exhausted, or a fatal exception.
    """
    last: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "异步生成器重试 %d/%d: %s，%.1fs 后重试",
                attempt,
                max_retries,
                last,
                delay,
            )
            await asyncio.sleep(delay)
        try:
            async for item in gen_factory(*a, **kw):
                yield item
            return
        except exceptions as e:
            if fatal_check is not None and fatal_check(e):
                raise
            last = e
    if last is not None:
        raise last
