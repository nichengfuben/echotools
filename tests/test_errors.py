from __future__ import annotations

import pytest

from echotools.errors import (
    EchoError,
    NotSupportedError,
    TimeoutError,
    ValidationError,
    classify_http_error,
)
from echotools.errors.http import (
    AuthError,
    ContextLengthError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError,
)


@pytest.mark.parametrize(
    "status,message,expected_type",
    [
        (400, "prompt is too long", ContextLengthError),
        (400, "bad request", ValidationError),
        (401, "unauthorized", AuthError),
        (402, "payment required", QuotaExceededError),
        (404, "missing", NotFoundError),
        (408, "timeout", TimeoutError),
        (429, "rate limit", RateLimitError),
        (501, "not implemented", NotSupportedError),
        (503, "unavailable", ServerError),
        (418, "teapot", EchoError),
    ],
)
def test_classify_http_error(status, message, expected_type) -> None:
    err = classify_http_error(status, message)
    assert isinstance(err, expected_type)


def test_echo_error_attributes() -> None:
    err = EchoError("boom", status_code=500)
    assert err.message == "boom"
    assert err.status_code == 500
