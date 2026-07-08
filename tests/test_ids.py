from __future__ import annotations

import pytest

from echotools.ids import short_id, span_id, trace_id, uuid7


def test_uuid7_format() -> None:
    value = uuid7()
    assert len(value) == 36
    assert value.count("-") == 4


def test_short_id_length() -> None:
    assert len(short_id(8)) == 8


def test_short_id_invalid_length() -> None:
    with pytest.raises(ValueError):
        short_id(0)


def test_trace_and_span_ids() -> None:
    assert len(trace_id()) == 32
    assert len(span_id()) == 16
