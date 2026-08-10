from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from scenes.manager import SceneManager


class Scene(ABC):
    """One screen of the app. Scenes own their window and are driven by the SceneManager."""

    def __init__(self, manager: SceneManager):
        self.manager = manager
        self.window: pygame.window.Window | None = None

    @abstractmethod
    def enter(self) -> None:
        """Called when this scene becomes active. Create window here."""

    @abstractmethod
    def exit(self) -> None:
        """Called when leaving this scene. Destroy window here."""

    def handle_event(self, event: pygame.event.Event) -> None:  # noqa: B027
        """Handle a single pygame event. Override for pygame scenes."""

    def update(self) -> None:  # noqa: B027
        """Update scene state (called once per frame). Override for pygame scenes."""

    def draw(self, surface: pygame.Surface) -> None:  # noqa: B027
        """Draw the scene onto the given surface. Override for pygame scenes."""
