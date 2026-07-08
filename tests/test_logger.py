from __future__ import annotations

import logging
import os

from echotools.logger import LoggerManager, configure, get_logger, set_color


def test_get_logger_returns_logger() -> None:
    log = get_logger("test.module")
    assert isinstance(log, logging.Logger)


def test_configure_sets_level() -> None:
    import logging

    configure(level="DEBUG")
    assert logging.getLogger().level <= logging.DEBUG


def test_logger_manager_file_handler(tmp_path) -> None:
    mgr = LoggerManager()
    log_file = tmp_path / "app.log"
    mgr.configure(level="INFO", log_file=str(log_file))
    logger = mgr.get_logger("test")
    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()
    assert log_file.exists()


def test_set_color_respects_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    set_color(False)
    mgr = LoggerManager()
    mgr.configure(level="INFO", color=True)
    assert os.environ.get("NO_COLOR") == "1"
