from __future__ import annotations

"""Span 与 Trace 实现。"""

import time
from typing import Any, Dict, List, Optional

from echotools.base.ids.generator import span_id as gen_span_id
from echotools.base.ids.generator import trace_id as gen_trace_id

__all__ = ["Span", "Trace"]


class Span:
    """单个调用片段。"""

    __slots__ = (
        "name",
        "span_id",
        "trace_id",
        "parent_id",
        "start_time",
        "end_time",
        "tags",
        "logs",
        "_finished",
    )

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_id: Optional[str] = None,
    ) -> None:
        """初始化 Span。

        Args:
            name: span 名称。
            trace_id: 所属 trace。
            parent_id: 父 span id。
        """
        self.name = name
        self.span_id = gen_span_id()
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.tags: Dict[str, Any] = {}
        self.logs: List[Dict[str, Any]] = []
        self._finished = False

    def set_tag(self, key: str, value: Any) -> "Span":
        """设置标签。"""
        self.tags[key] = value
        return self

    def log(self, message: str, **fields: Any) -> "Span":
        """记录一条 span 日志。"""
        entry = {"time": time.time(), "message": message}
        entry.update(fields)
        self.logs.append(entry)
        return self

    def finish(self) -> None:
        """结束 span（幂等）。"""
        if self._finished:
            return
        self.end_time = time.time()
        self._finished = True

    @property
    def duration(self) -> float:
        """span 持续时间（秒）。"""
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "name": self.name,
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": round(self.duration, 6),
            "tags": dict(self.tags),
            "logs": list(self.logs),
        }

    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.set_tag("error", True)
            self.set_tag("error.type", getattr(exc_type, "__name__", ""))
        self.finish()


class Trace:
    """一次完整调用链。"""

    __slots__ = ("trace_id", "spans", "_span_stack")

    def __init__(self, trace_id: Optional[str] = None) -> None:
        """初始化 Trace。

        Args:
            trace_id: 指定 trace_id，缺省时自动生成。
        """
        self.trace_id = trace_id or gen_trace_id()
        self.spans: List[Span] = []
        self._span_stack: List[Span] = []

    def start_span(self, name: str) -> Span:
        """开启一个 span，自动挂接当前父 span。"""
        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        span = Span(name, self.trace_id, parent_id)
        self.spans.append(span)
        self._span_stack.append(span)
        return span

    def finish_span(self, span: Span) -> None:
        """结束指定 span 并出栈。"""
        span.finish()
        if self._span_stack and self._span_stack[-1] is span:
            self._span_stack.pop()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "trace_id": self.trace_id,
            "spans": [s.to_dict() for s in self.spans],
        }
