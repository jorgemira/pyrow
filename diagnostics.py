"""Logging and crash reporting, for working out afterwards what went wrong.

PyRow is a full-screen app people run and then stop looking at, often on a machine that is not the
one they develop on. "It crashed" therefore has to be answerable from a file rather than from
whatever scrolled past in a terminal that is now closed. Everything goes to a rotating log under
:func:`log_dir`, and uncaught exceptions — on the main thread *and* on any worker — are written
there before the process dies.

The log is meant to be read later by someone who was not present, so a run opens with a banner of
everything that is awkward to reconstruct after the fact: versions, the display layout, and when
this copy of the code was last written.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

LOGGER_NAME = "pyrow"
LOG_FILENAME = "pyrow.log"
#: Four megabytes in total: ample at INFO, and a hard ceiling if someone turns on DEBUG.
MAX_BYTES = 1_000_000
BACKUP_COUNT = 3

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_log = logging.getLogger(LOGGER_NAME)


def log_dir() -> Path:
    """Where logs live: ``PYROW_LOG_DIR``, else the XDG state directory, else ``~/.local/state``.

    State rather than cache: a log you would have wanted after a crash is not disposable.
    """
    override = os.environ.get("PYROW_LOG_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base).expanduser() / "pyrow"


def log_file() -> Path:
    return log_dir() / LOG_FILENAME


def setup_logging(level: str | int | None = None, console_level: int = logging.WARNING) -> Path | None:
    """Send logging to a rotating file plus the console. Returns the file, or None if unavailable.

    Idempotent, so a second call reconfigures rather than doubling every line.
    ``PYROW_LOG_LEVEL`` raises or lowers the file level without a code change.
    """
    if level is None:
        level = os.environ.get("PYROW_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(min(level, console_level))
    for handler in [h for h in root.handlers if getattr(h, "_pyrow", False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(console_level)
    console.setFormatter(formatter)
    console._pyrow = True  # ty: ignore[unresolved-attribute]
    root.addHandler(console)

    path = log_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    except OSError as e:
        # A read-only or unwritable home is not a reason to refuse to start.
        _log.warning("cannot write a log file at %s (%s); logging to the console only", path, e)
        return None

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._pyrow = True  # ty: ignore[unresolved-attribute]
    root.addHandler(file_handler)
    return path


def install_crash_handlers() -> None:
    """Write uncaught exceptions to the log before the process dies.

    Both hooks matter: an exception escaping a worker thread would otherwise only ever reach a
    stderr nobody is reading.
    """
    previous_hook = sys.excepthook

    def log_uncaught(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            _log.critical("uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        previous_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = log_uncaught

    previous_thread_hook = threading.excepthook

    def log_uncaught_in_thread(args):
        _log.critical(
            "uncaught exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        previous_thread_hook(args)

    threading.excepthook = log_uncaught_in_thread


def deployed_at() -> str:
    """When this copy of the code was last written, as a stand-in for a version.

    PyRow is not installed as a package and is often copied to the machine that runs it without a
    ``.git`` directory, so there is no commit to report — but the newest file mtime does answer
    "is this running what I think I deployed?".
    """
    try:
        newest = max(p.stat().st_mtime for p in Path(__file__).parent.glob("*.py"))
    except OSError, ValueError:
        return "unknown"
    return datetime.fromtimestamp(newest, UTC).strftime("%Y-%m-%d %H:%M UTC")


def log_session_start(extra: dict[str, object] | None = None) -> None:
    """Open the log with the facts that are painful to reconstruct after the event."""
    _log.info("=" * 72)
    facts: dict[str, object] = {
        "pid": os.getpid(),
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "node": platform.node(),
        "code deployed": deployed_at(),
        "log file": log_file(),
    }
    facts.update(_graphics_facts())
    if extra:
        facts.update(extra)
    for key, value in facts.items():
        _log.info("  %-20s %s", key, value)


def _graphics_facts() -> dict[str, object]:
    """Versions and displays: between them they explain most layout and rendering reports."""
    try:
        import pygame
    except ImportError:  # pragma: no cover - pygame is a hard dependency of the app
        return {"pygame": "not installed"}

    facts: dict[str, object] = {"pygame": pygame.version.ver, "sdl": ".".join(str(n) for n in pygame.get_sdl_version())}
    try:
        facts["displays"] = pygame.display.get_desktop_sizes()
    except pygame.error as e:
        facts["displays"] = f"unavailable ({e})"
    return facts
