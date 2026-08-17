from __future__ import annotations

import logging

import pygame

from diagnostics import install_crash_handlers, log_session_start, setup_logging
from scenes.manager import SceneManager
from scenes.menu import MenuScene

_log = logging.getLogger("pyrow.main")


def main() -> None:
    """Initialise pygame and run the menu, then whatever scene it hands over to."""
    # Logging first, so anything that goes wrong from here on is recoverable from the log rather
    # than from a terminal that has since been closed.
    setup_logging()
    install_crash_handlers()

    _, failed = pygame.init()
    if failed:
        # Usually the mixer on a machine with no audio device: the pacer still works, silently.
        _log.warning("%s pygame module(s) failed to initialise; sound may be unavailable", failed)
    pygame.display.set_allow_screensaver(True)
    log_session_start({"pygame init failures": failed})

    manager = SceneManager()
    clean = False
    try:
        manager.run(MenuScene(manager))
        clean = True
    except BaseException as e:
        # No traceback here: install_crash_handlers() logs that. This line exists only to name the
        # failure at the point that knows the run is over.
        _log.critical("session failing on %s", type(e).__name__)
        raise
    finally:
        # Two distinct endings on purpose: reading a log later, "was this a clean exit?" is the
        # first question, and a single ambiguous "session ended" cannot answer it.
        _log.info("session ended cleanly" if clean else "session ended after a failure")
        logging.shutdown()


if __name__ == "__main__":
    main()
