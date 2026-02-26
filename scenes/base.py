from abc import ABC, abstractmethod


class Scene(ABC):
    def __init__(self, manager):
        self.manager = manager
        self.window = None

    @abstractmethod
    def enter(self):
        """Called when this scene becomes active. Create window here."""

    @abstractmethod
    def exit(self):
        """Called when leaving this scene. Destroy window here."""

    def handle_event(self, event):
        """Handle a single pygame event. Override for pygame scenes."""

    def update(self):
        """Update scene state (called once per frame). Override for pygame scenes."""

    def draw(self, surface):
        """Draw the scene onto the given surface. Override for pygame scenes."""
