from __future__ import annotations

from echotools.exec.fncall.protocols.entml_thinking_history import (
    apply_thinking_history_policy,
    extract_reasoning_text,
    parse_interleaved_history,
)


def test_parse_interleaved_history_from_thinking_object() -> None:
    body = {"thinking": {"mode": "on", "interleaved_history": True}}
    assert parse_interleaved_history(body) is True
    assert parse_interleaved_history({"thinking": {"interleaved_history": False}}) is False


def test_parse_interleaved_history_top_level() -> None:
    assert parse_interleaved_history({"interleaved_history": True}) is True
    assert parse_interleaved_history({}, extra={"interleaved_history": True}) is True


def test_strip_reasoning_fields_when_disabled() -> None:
    msgs = [
        {
            "role": "assistant",
            "content": "answer",
            "reasoning": "thought",
            "reasoning_content": "thought",
        }
    ]
    out = apply_thinking_history_policy(msgs, False)
    assert out[0]["content"] == "answer"
    assert "reasoning" not in out[0]


def test_strip_entropy_thinking_blocks_when_disabled() -> None:
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "step 1"},
                {"type": "text", "text": "hello"},
            ],
        }
    ]
    out = apply_thinking_history_policy(msgs, False)
    assert out[0]["content"] == "hello"
    assert "reasoning" not in out[0]


def test_preserve_entropy_thinking_blocks_when_enabled() -> None:
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "step 1"},
                {"type": "text", "text": "hello"},
            ],
        }
    ]
    out = apply_thinking_history_policy(msgs, True)
    assert out[0]["reasoning"] == "step 1"
    assert out[0]["reasoning_content"] == "step 1"
    assert out[0]["content"][0]["type"] == "thinking"


def test_extract_reasoning_text_from_blocks() -> None:
    msg = {
        "role": "assistant",
        "content": [{"type": "thinking", "thinking": "a"}, {"type": "text", "text": "b"}],
    }
    assert extract_reasoning_text(msg) == "a"
