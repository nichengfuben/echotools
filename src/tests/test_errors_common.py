from __future__ import annotations

import pytest

from echotools.base.errors.common import (
    ConfigError,
    NetworkError,
    NoCandidateError,
    PluginError,
    ProtocolError,
)


def test_error_hierarchy_messages() -> None:
    assert ConfigError("cfg").message == "cfg"
    assert NetworkError("net").message == "net"
    assert NoCandidateError("none").message == "none"
    assert PluginError("plug").message == "plug"
    assert ProtocolError("proto").message == "proto"


def test_no_candidate_is_exception() -> None:
    with pytest.raises(NoCandidateError):
        raise NoCandidateError("fail")
