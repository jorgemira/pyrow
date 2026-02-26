import pygame


class SceneManager:
    def __init__(self):
        self.current_scene = None
        self.running = False
        self.clock = pygame.time.Clock()
        self._pending_scene = None

    def switch_to(self, scene):
        self._pending_scene = scene

    def quit(self):
        self.running = False

    def run(self, initial_scene):
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

            # Pygame scene loop: only runs if scene has a window
            if self.current_scene.window:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    else:
                        self.current_scene.handle_event(event)

                self.current_scene.update()

                surface = self.current_scene.window.get_surface()
                self.current_scene.draw(surface)
                self.current_scene.window.flip()

                self.clock.tick(60)

        if self.current_scene:
            self.current_scene.exit()
        pygame.quit()
