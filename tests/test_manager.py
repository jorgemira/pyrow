"""Tests for the scene loop: switching, teardown order and quitting."""

from __future__ import annotations

import pygame
import pytest

from scenes.base import Scene
from scenes.manager import SceneManager


class RecordingScene(Scene):
    """A windowless scene that records lifecycle calls and can drive the manager."""

    def __init__(self, manager, log: list[str], name: str, on_enter=None):
        super().__init__(manager)
        self.log = log
        self.name = name
        self._on_enter = on_enter
        self.frames = 0

    def enter(self):
        self.log.append(f"enter:{self.name}")
        if self._on_enter:
            self._on_enter()

    def exit(self):
        self.log.append(f"exit:{self.name}")

    def update(self):
        self.frames += 1


@pytest.fixture
def manager(monkeypatch):
    """A manager whose pygame.quit() is stubbed, so tearing down does not kill the session."""
    monkeypatch.setattr(pygame, "quit", lambda: None)
    return SceneManager()


def test_the_initial_scene_is_entered_and_exited(manager):
    log: list[str] = []
    scene = RecordingScene(manager, log, "first", on_enter=manager.quit)

    manager.run(scene)

    assert log == ["enter:first", "exit:first"]


def test_switching_exits_the_old_scene_before_entering_the_new_one(manager):
    log: list[str] = []
    second = RecordingScene(manager, log, "second", on_enter=manager.quit)
    first = RecordingScene(manager, log, "first", on_enter=lambda: manager.switch_to(second))

    manager.run(first)

    assert log == ["enter:first", "exit:first", "enter:second", "exit:second"]
    assert manager.current_scene is second


def test_quit_during_enter_stops_before_any_frame_runs(manager):
    log: list[str] = []
    scene = RecordingScene(manager, log, "only", on_enter=manager.quit)

    manager.run(scene)

    assert scene.frames == 0
    assert manager.running is False


def test_a_windowless_scene_that_returns_does_not_spin(manager):
    """Without a window there is nothing to draw, so the loop must still be rate-limited."""

    class CountingClock:
        def __init__(self, stop_after):
            self.ticks: list[int] = []
            self._stop_after = stop_after

        def tick(self, fps):
            self.ticks.append(fps)
            if len(self.ticks) >= self._stop_after:
                manager.quit()
            return 16

    clock = CountingClock(stop_after=3)
    manager.clock = clock

    manager.run(RecordingScene(manager, [], "idle"))

    assert clock.ticks == [60, 60, 60], "the idle path must tick the clock rather than busy-wait"


def test_switch_queued_before_run_is_replaced_by_the_initial_scene(manager):
    """run() takes precedence: a stale queued scene must not preempt the one it was given."""
    log: list[str] = []
    stale = RecordingScene(manager, log, "stale")
    wanted = RecordingScene(manager, log, "wanted", on_enter=manager.quit)

    manager.switch_to(stale)
    manager.run(wanted)

    assert log == ["enter:wanted", "exit:wanted"]
