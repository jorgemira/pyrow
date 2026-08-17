"""Shared test setup.

pygame is forced onto SDL's dummy video/audio drivers so the animation scene can be built and
rendered in a test without a display or a sound card. tkinter has no such mode, so the
customtkinter tests are skipped unless a display is available (CI runs them under xvfb).
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402 - must follow the SDL environment setup

from scenes.manager import SceneManager  # noqa: E402 - imports pygame

HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
requires_display = pytest.mark.skipif(HAS_DISPLAY is False, reason="tkinter needs a display; use xvfb-run")

# Far outside any plausible desktop. A normal window would be clamped back on screen by the
# window manager; an override-redirect one is placed exactly here.
OFFSCREEN = "+6000+2000"


def hide_tk_windows(monkeypatch):
    """Keep every Tk window created during the tests off the visible desktop.

    tkinter has no dummy backend, so these tests map real windows. Three approaches were measured
    on a 4768x1440 two-monitor desktop:

    * plain off-screen geometry — the window manager clamps it back into view;
    * ``withdraw()`` — invisible, but then ``winfo_height()`` stays at 1, which breaks every
      assertion about scrolling and mapping;
    * ``wm_overrideredirect(True)`` plus off-screen geometry — bypasses the window manager, so the
      coordinates are honoured and the window is still laid out normally. That is what we use.

    (``-alpha 0`` was tried first and is silently ignored by this Tk/compositor combination.)
    """
    import tkinter as tk

    import customtkinter as ctk

    def banish(window):
        # Raw Tk methods on purpose: CTk overrides geometry() and it depends on scaling state that
        # is not set up yet when tk.Toplevel.__init__ runs inside a CTkToplevel subclass.
        try:
            tk.Wm.wm_overrideredirect(window, True)
            tk.Wm.wm_geometry(window, OFFSCREEN)
        except tk.TclError:
            pass

    for cls in (ctk.CTk, ctk.CTkToplevel, tk.Toplevel):
        original_init = cls.__init__

        def quiet_init(self, *args, _original_init=original_init, **kwargs):
            _original_init(self, *args, **kwargs)
            banish(self)

        monkeypatch.setattr(cls, "__init__", quiet_init)


class StubManager(SceneManager):
    """A SceneManager that records switches instead of running the event loop."""

    def __init__(self):
        super().__init__()
        self.switched_to = None
        self.quit_called = False

    def switch_to(self, scene):
        self.switched_to = scene

    def quit(self):
        self.quit_called = True


def stub_ctk_lifecycle(monkeypatch):
    """Neuter CTk.mainloop/destroy so a scene's enter() returns with its widgets still alive.

    Returns the real destroy, for tearing the window down afterwards.
    """
    import customtkinter as ctk

    original_destroy = ctk.CTk.destroy
    monkeypatch.setattr(ctk.CTk, "mainloop", lambda self, *a, **k: None)
    monkeypatch.setattr(ctk.CTk, "destroy", lambda self: None)
    hide_tk_windows(monkeypatch)
    return original_destroy


def sample_library():
    """A small deterministic library, long enough that the list scrolls.

    The tests must not depend on the shipped workouts.json, and a 116-row list makes every menu
    test pay ~2s just to build its widgets.
    """
    from models.workout import Level, Section, Workout

    levels = [Level.beginner, Level.intermediate, Level.advanced]
    minutes = [15, 25, 35, 50]
    return [
        Workout(
            name=f"{level.label} - Sample {variant}{i} - {mins}min",
            description=f"A {mins} minute {level.label.lower()} session",
            level=level,
            sections=[Section(duration=mins * 60, stroke_rate=20 + i)],
        )
        for i, (level, mins, variant) in enumerate((lv, m, v) for lv in levels for m in minutes for v in "abc")
    ]


@pytest.fixture(autouse=True)
def _isolated_logs(monkeypatch, tmp_path):
    """Never write to the real log directory, and never leave handlers behind.

    setup_logging() reconfigures the root logger, so without the teardown one test's handlers would
    still be attached — and writing to a closed temporary file — during the next.
    """
    import logging

    monkeypatch.setenv("PYROW_LOG_DIR", str(tmp_path / "logs"))
    before = list(logging.getLogger().handlers)
    yield
    root = logging.getLogger()
    for handler in [h for h in root.handlers if h not in before]:
        root.removeHandler(handler)
        handler.close()


@pytest.fixture(scope="session", autouse=True)
def _pygame_session():
    import pygame

    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def stub_manager():
    return StubManager()


@pytest.fixture(scope="module")
def _menu_scene_shared():
    """Build the menu once per module — a Tk root plus its widgets costs about a second."""
    from scenes import menu as menu_module

    with pytest.MonkeyPatch.context() as mp:
        original_destroy = stub_ctk_lifecycle(mp)
        saved: list[list] = []
        mp.setattr(menu_module, "load_workouts", sample_library)
        mp.setattr(menu_module, "save_workouts", lambda workouts: saved.append(list(workouts)))

        scene = menu_module.MenuScene(StubManager())
        scene.enter()
        scene.saved = saved  # ty: ignore[unresolved-attribute]
        scene._root.geometry(OFFSCREEN)
        scene._root.update_idletasks()
        yield scene
        original_destroy(scene._root)


@pytest.fixture
def menu_scene(_menu_scene_shared):
    """The shared menu, reset to a known state so tests stay independent."""
    from scenes.menu import _REF_H, _REF_W

    scene = _menu_scene_shared
    scene.workouts = sample_library()
    scene.saved.clear()
    scene.manager.switched_to = None
    scene.manager.quit_called = False
    scene._selected = None
    scene._level_var.set("All")
    scene._duration_var.set("All")
    scene._ui_scale = min(scene._root.winfo_width() / _REF_W, scene._root.winfo_height() / _REF_H)
    scene._apply_fonts()
    scene._refresh_list()
    scene._list_frame._parent_canvas.yview_moveto(0.0)
    scene._scroller.sync()
    scene._tooltip.cancel()
    scene._root.update_idletasks()
    return scene


@pytest.fixture
def ctk_root(monkeypatch):
    """A bare customtkinter root for testing dialogs."""
    import customtkinter as ctk

    original_destroy = stub_ctk_lifecycle(monkeypatch)
    root = ctk.CTk()
    root.geometry(OFFSCREEN)
    root.update_idletasks()
    yield root
    original_destroy(root)
