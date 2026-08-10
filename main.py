from __future__ import annotations

import sys

import pygame

from scenes.manager import SceneManager
from scenes.menu import MenuScene


def main() -> None:
    """Initialise pygame and run the menu, then whatever scene it hands over to."""
    _, failed = pygame.init()
    if failed:
        # Usually the mixer on a machine with no audio device: the pacer still works, silently.
        print(f"pyrow: {failed} pygame module(s) failed to initialise; sound may be unavailable", file=sys.stderr)
    pygame.display.set_allow_screensaver(True)
    manager = SceneManager()
    manager.run(MenuScene(manager))


if __name__ == "__main__":
    main()
