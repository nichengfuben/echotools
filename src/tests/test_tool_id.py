from __future__ import annotations

import pytest

from echotools.base.ids import gen_tool_id
from echotools.exec.fncall.tool_id import (
    ensure_toolu_tool_call_id,
    fix_tool_call_id,
    is_placeholder_tool_call_id,
)


def test_gen_tool_id_format() -> None:
    tid = gen_tool_id()
    assert tid.startswith("toolu_")
    assert len(tid) == len("toolu_") + 24


def test_is_placeholder_tool_call_id() -> None:
    assert is_placeholder_tool_call_id("")
    assert is_placeholder_tool_call_id("call_0000")
    assert is_placeholder_tool_call_id("toolu_call_0001")
    assert is_placeholder_tool_call_id("call_abc")
    assert not is_placeholder_tool_call_id("toolu_real123")


def test_fix_tool_call_id_replaces_placeholder() -> None:
    fixed = fix_tool_call_id({
        "id": "call_0000",
        "function": {"name": "search", "arguments": '{"q":"x"}'},
    })
    assert fixed["id"].startswith("toolu_")
    assert fixed["function"]["name"] == "search"


def test_fix_tool_call_id_keeps_valid() -> None:
    fixed = fix_tool_call_id({
        "id": "toolu_abc123",
        "function": {"name": "search", "arguments": "{}"},
    })
    assert fixed["id"] == "toolu_abc123"


def test_ensure_toolu_tool_call_id() -> None:
    assert ensure_toolu_tool_call_id("call_0000").startswith("toolu_")
    assert ensure_toolu_tool_call_id("abc") == "toolu_abc"
    assert ensure_toolu_tool_call_id("toolu_xyz") == "toolu_xyz"
