import pygame

from scenes.manager import SceneManager
from scenes.menu import MenuScene


def main():
    pygame.init()
    manager = SceneManager()
    manager.run(MenuScene(manager))


if __name__ == "__main__":
    main()
