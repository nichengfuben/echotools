from __future__ import annotations

"""Tracer：调用链入口，集成 contextvars。"""

import contextlib
from typing import Any, Callable, Iterator, List, Optional

from echotools.tracing.context import (
    set_current_span_id,
    set_current_trace_id,
)
from echotools.tracing.span import Span, Trace

__all__ = ["Tracer"]


class Tracer:
    """调用链追踪器。

    支持创建 trace、span 上下文管理、可选导出回调。
    """

    def __init__(
        self,
        on_finish: Optional[Callable[[Trace], None]] = None,
    ) -> None:
        """初始化 Tracer。

        Args:
            on_finish: trace 完成回调，用于导出。
        """
        self._on_finish = on_finish
        self._active: List[Trace] = []

    def start_trace(self, trace_id: Optional[str] = None) -> Trace:
        """创建并激活一个新 trace。"""
        trace = Trace(trace_id)
        self._active.append(trace)
        set_current_trace_id(trace.trace_id)
        return trace

    def finish_trace(self, trace: Trace) -> None:
        """结束 trace 并触发导出回调。"""
        for span in trace.spans:
            span.finish()
        if trace in self._active:
            self._active.remove(trace)
        if self._on_finish is not None:
            self._on_finish(trace)

    @contextlib.contextmanager
    def trace(self, name: str = "root") -> Iterator[Trace]:
        """trace 上下文管理器。

        Args:
            name: 根 span 名称。

        Yields:
            Trace 实例。
        """
        trace = self.start_trace()
        root = trace.start_span(name)
        token = set_current_span_id(root.span_id)
        try:
            yield trace
        except Exception:
            root.set_tag("error", True)
            raise
        finally:
            trace.finish_span(root)
            set_current_span_id(token.old_value if hasattr(token, "old_value") else None)
            self.finish_trace(trace)

    @contextlib.contextmanager
    def span(self, trace: Trace, name: str) -> Iterator[Span]:
        """span 上下文管理器。

        Args:
            trace: 所属 trace。
            name: span 名称。

        Yields:
            Span 实例。
        """
        span = trace.start_span(name)
        token = set_current_span_id(span.span_id)
        try:
            yield span
        except Exception:
            span.set_tag("error", True)
            raise
        finally:
            trace.finish_span(span)
            try:
                set_current_span_id(token.old_value)  # type: ignore[attr-defined]
            except AttributeError:
                set_current_span_id(span.parent_id)
