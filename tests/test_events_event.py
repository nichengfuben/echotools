from __future__ import annotations

from dataclasses import dataclass

from echotools.events import Event


@dataclass
class DemoEvent(Event):
    value: str = ""


def test_event_name_and_to_dict() -> None:
    ev = DemoEvent(value="ok")
    d = ev.to_dict()
    assert d["event"] == "DemoEvent"
    assert d["value"] == "ok"
    assert "timestamp" in d
