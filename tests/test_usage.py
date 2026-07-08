from __future__ import annotations

from echotools.dispatch.usage import fallback_usage, normalize_usage


def test_fallback_usage() -> None:
    u = fallback_usage(30, "hello world")
    assert u["prompt_tokens"] >= 1
    assert u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]


def test_normalize_openai_usage() -> None:
    u = normalize_usage(
        {"prompt_tokens": 10, "completion_tokens": 5},
        prompt_len=100,
        resp_text="x",
    )
    assert u["total_tokens"] == 15


def test_normalize_anthropic_usage() -> None:
    u = normalize_usage(
        {"input_tokens": 8, "output_tokens": 4},
        prompt_len=100,
        resp_text="x",
    )
    assert u["completion_tokens"] == 4


def test_normalize_invalid_falls_back() -> None:
    u = normalize_usage(None, 30, "response text")
    assert u["completion_tokens"] >= 0


def test_normalize_type_error_falls_back() -> None:
    u = normalize_usage({"prompt_tokens": "bad", "completion_tokens": "bad"}, 30, "x")
    assert u["total_tokens"] >= 1
