"""Tests for logging and crash reporting.

The point of this module is that a failure nobody watched can be diagnosed afterwards, so what is
asserted here is mostly "did it actually reach the file".
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

import pytest

from diagnostics import (
    BACKUP_COUNT,
    MAX_BYTES,
    deployed_at,
    install_crash_handlers,
    log_dir,
    log_file,
    log_session_start,
    setup_logging,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_log_directory_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PYROW_LOG_DIR", str(tmp_path / "explicit"))
    assert log_dir() == tmp_path / "explicit"

    monkeypatch.delenv("PYROW_LOG_DIR")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert log_dir() == tmp_path / "state" / "pyrow"

    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "home"))
    assert log_dir() == tmp_path / "home" / ".local" / "state" / "pyrow"


def test_messages_reach_the_file():
    path = setup_logging()
    assert path is not None

    logging.getLogger("pyrow.test").info("a thing happened")

    assert "a thing happened" in read(path)


def test_the_level_can_be_raised_from_the_environment(monkeypatch):
    monkeypatch.setenv("PYROW_LOG_LEVEL", "DEBUG")
    path = setup_logging()
    assert path is not None

    logging.getLogger("pyrow.test").debug("fine detail")

    assert "fine detail" in read(path)


def test_debug_is_dropped_by_default():
    path = setup_logging()
    assert path is not None

    logging.getLogger("pyrow.test").debug("fine detail")

    assert "fine detail" not in read(path)


def test_configuring_twice_does_not_double_every_line():
    setup_logging()
    path = setup_logging()
    assert path is not None

    logging.getLogger("pyrow.test").warning("only once")

    assert read(path).count("only once") == 1


def test_the_log_is_capped_so_it_cannot_fill_the_disk():
    setup_logging()
    handlers = [h for h in logging.getLogger().handlers if isinstance(h, logging.handlers.RotatingFileHandler)]

    assert handlers, "there should be a rotating file handler"
    assert handlers[0].maxBytes == MAX_BYTES
    assert handlers[0].backupCount == BACKUP_COUNT
    assert MAX_BYTES * (BACKUP_COUNT + 1) < 10_000_000, "the total ceiling should stay modest"


def test_an_unwritable_directory_does_not_stop_the_app(monkeypatch, tmp_path):
    """A log is worth having, but not worth refusing to start over."""
    blocker = tmp_path / "blocked"
    blocker.write_text("I am a file, not a directory")
    monkeypatch.setenv("PYROW_LOG_DIR", str(blocker / "logs"))

    assert setup_logging() is None
    logging.getLogger("pyrow.test").warning("still runs")  # must not raise


def test_an_uncaught_exception_is_logged_with_its_traceback():
    path = setup_logging()
    assert path is not None
    install_crash_handlers()

    try:
        raise ValueError("the thing that broke")
    except ValueError as e:
        sys.excepthook(type(e), e, e.__traceback__)

    written = read(path)
    assert "uncaught exception" in written
    assert "the thing that broke" in written
    assert "ValueError" in written, "the traceback itself has to be there, not just the message"


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_crash_on_a_worker_thread_is_logged_too():
    """Nobody is watching a background thread's stderr."""
    path = setup_logging()
    assert path is not None
    install_crash_handlers()

    def explode():
        raise RuntimeError("the worker fell over")

    thread = threading.Thread(target=explode, name="pyrow-worker")
    thread.start()
    thread.join()

    written = read(path)
    assert "pyrow-worker" in written
    assert "the worker fell over" in written


def test_a_keyboard_interrupt_is_not_reported_as_a_crash():
    path = setup_logging()
    assert path is not None
    install_crash_handlers()

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt as e:
        sys.excepthook(type(e), e, e.__traceback__)

    assert "uncaught exception" not in read(path)


def test_the_banner_records_what_is_hard_to_reconstruct_later():
    path = setup_logging()
    assert path is not None

    log_session_start({"pygame init failures": 0})

    written = read(path)
    for fact in ("pid", "python", "platform", "code deployed", "pygame", "sdl", "displays"):
        assert fact in written, f"the banner should record {fact}"


def test_the_deploy_stamp_is_a_date_not_a_guess():
    stamp = deployed_at()
    assert stamp != "unknown"
    assert "UTC" in stamp


def test_the_log_file_sits_inside_the_log_directory():
    assert log_file().parent == log_dir()
