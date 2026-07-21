from __future__ import annotations

from echotools.media.tracing import Tracer, get_current_trace_id


def test_trace_creates_spans() -> None:
    """trace 上下文创建并完成 span。"""
    tracer = Tracer()
    with tracer.trace("root") as trace:
        with tracer.span(trace, "child") as span:
            span.set_tag("k", "v")
        assert get_current_trace_id() == trace.trace_id
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "root"
    assert trace.spans[1].tags["k"] == "v"
    assert trace.spans[1].duration >= 0


def test_span_error_tag() -> None:
    """异常时 span 标记 error。"""
    tracer = Tracer()
    trace = tracer.start_trace()
    span = trace.start_span("err")
    try:
        with span:
            raise ValueError("boom")
    except ValueError:
        pass
    assert span.tags.get("error") is True
    tracer.finish_trace(trace)
