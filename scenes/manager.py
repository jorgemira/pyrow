from __future__ import annotations

import logging

import pygame

from scenes.base import Scene

FPS = 60

_log = logging.getLogger("pyrow.scenes")


class SceneManager:
    """Owns the frame loop and hands control to whichever Scene is active."""

    def __init__(self):
        self.current_scene: Scene | None = None
        self.running = False
        self.clock = pygame.time.Clock()
        self._pending_scene: Scene | None = None

    def switch_to(self, scene: Scene) -> None:
        """Queue *scene* to replace the current one at the start of the next iteration."""
        self._pending_scene = scene

    def quit(self) -> None:
        self.running = False

    def run(self, initial_scene: Scene) -> None:
        """Run scenes until one quits, then tear the active scene down."""
        self.running = True
        self._pending_scene = initial_scene

        while self.running:
            if self._pending_scene is not None:
                self._activate_pending()
                continue

            scene = self.current_scene
            window = scene.window if scene else None
            if scene is None or window is None:
                # A windowless scene (the customtkinter menu) runs its own event loop inside
                # enter(). Ticking keeps this loop from spinning at 100% CPU if one returns
                # without queueing a successor.
                self.clock.tick(FPS)
                continue

            self._run_frame(scene, window)

        if self.current_scene:
            self.current_scene.exit()
        pygame.quit()

    def _activate_pending(self) -> None:
        pending = self._pending_scene
        assert pending is not None
        if self.current_scene:
            _log.info("leaving %s", type(self.current_scene).__name__)
            self.current_scene.exit()
        self.current_scene = pending
        self._pending_scene = None
        _log.info("entering %s", type(pending).__name__)
        pending.enter()

    def _run_frame(self, scene: Scene, window: pygame.window.Window) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            else:
                scene.handle_event(event)

        scene.update()
        scene.draw(window.get_surface())
        window.flip()
        self.clock.tick(FPS)
