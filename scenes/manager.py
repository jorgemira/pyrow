from __future__ import annotations

import pygame

from scenes.base import Scene


class SceneManager:
    def __init__(self):
        self.current_scene: Scene | None = None
        self.running = False
        self.clock = pygame.time.Clock()
        self._pending_scene: Scene | None = None

    def switch_to(self, scene: Scene):
        self._pending_scene = scene

    def quit(self):
        self.running = False

    def run(self, initial_scene: Scene):
        self.running = True
        self._pending_scene = initial_scene

        while self.running:
            if self._pending_scene:
                if self.current_scene:
                    self.current_scene.exit()
                self.current_scene = self._pending_scene
                self._pending_scene = None
                self.current_scene.enter()
                continue

            if not self.running or self._pending_scene:
                continue

            scene = self.current_scene
            if scene is None:
                continue

            # Pygame scene loop: only runs if scene has a window
            if scene.window:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    else:
                        scene.handle_event(event)

                scene.update()

                surface = scene.window.get_surface()
                scene.draw(surface)
                scene.window.flip()

                self.clock.tick(60)

        if self.current_scene:
            self.current_scene.exit()
        pygame.quit()
