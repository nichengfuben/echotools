from __future__ import annotations

from pathlib import Path

from echotools.io import atomic_write_text, ensure_directory, read_text_if_exists


def test_atomic_write_and_read(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_read_text_if_exists_missing(tmp_path: Path) -> None:
    assert read_text_if_exists(tmp_path / "missing.txt") is None


def test_ensure_directory(tmp_path: Path) -> None:
    d = ensure_directory(tmp_path / "a" / "b")
    assert d.is_dir()
