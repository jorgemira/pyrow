"""Tests for the pacer scene: layout invariants, interaction state and a full render pass.

These run headless on SDL's dummy video driver, so they exercise the real window, fonts and
draw calls without needing a display.
"""

from __future__ import annotations

import pygame
import pytest

from animations.base import DRILL_PROFILES
from models.workout import DrillEntry, DrillType, Level, Section, SectionType, Workout
from scenes.animation import BG_COLOR, AnimationScene
from workout_player import PlayerState


def long_workout() -> Workout:
    """A workout with enough sections that the "Up next" list overflows."""
    return Workout(
        name="Advanced - Layout Probe - Long Name That Overflows The Panel",
        level=Level.advanced,
        sections=[
            Section(duration=120, stroke_rate=18, section_type=SectionType.warmup),
            Section(
                duration=60,
                stroke_rate=28,
                tension=5,
                repeats=8,
                rest_after=20,
                drills=[DrillEntry(DrillType.pause_arms_away, 2), DrillEntry(DrillType.none, 2)],
            ),
            Section(duration=120, stroke_rate=18, section_type=SectionType.cooldown),
        ],
    )


@pytest.fixture
def scene(stub_manager):
    scene = AnimationScene(stub_manager, workout=long_workout())
    scene.enter()
    yield scene
    scene.exit()


@pytest.fixture
def surface(scene):
    return scene.window.get_surface()


def render(scene, surface):
    scene.update()
    scene.draw(surface)


class TestWindow:
    def test_title_names_the_workout(self, scene):
        assert scene.workout.name in scene.window.title

    def test_window_ends_up_usable(self, scene):
        """The window is created hidden and shown after positioning.

        That sequence itself is not assertable — pygame's Window is an immutable C type, so show()
        cannot be spied on and ``hidden`` is write-only — but a window that was never shown would
        still hand back a surface, so this only guards the surface being renderable.
        """
        assert scene.window.get_surface().get_size() == (scene.sw, scene.sh)


class TestBarLayout:
    def test_hit_rects_contain_their_bars(self, scene):
        """A bar that extends past its own hit rect has pixels that look draggable but are not."""
        section_bar = pygame.Rect(scene._bar_x, scene._sec_bar_y, scene._bar_w, scene._bar_h)
        total_bar = pygame.Rect(scene._bar_x, scene._total_bar_y, scene._bar_w, scene._bar_h)

        assert scene._section_bar_rect.contains(section_bar)
        assert scene._total_bar_rect.contains(total_bar)

    def test_hit_rects_do_not_overlap(self, scene):
        assert not scene._section_bar_rect.colliderect(scene._total_bar_rect)

    def test_hit_rects_leave_no_dead_space(self, scene):
        union = scene._section_bar_rect.union(scene._total_bar_rect)

        assert union.height == scene._bar_rect.height
        assert union.top == scene._bar_rect.top

    def test_bar_at_maps_positions_to_the_right_bar(self, scene):
        assert scene._bar_at((scene._bar_x + 5, scene._sec_bar_y)) == "section"
        assert scene._bar_at((scene._bar_x + 5, scene._total_bar_y)) == "total"
        assert scene._bar_at((scene._panel_rect.centerx, scene._panel_rect.centery)) is None

    def test_progress_from_mouse_clamps_outside_the_bar(self, scene):
        assert scene._bar_progress_from_mouse(scene._bar_x - 500) == 0.0
        assert scene._bar_progress_from_mouse(scene._bar_x + scene._bar_w + 500) == 1.0
        assert scene._bar_progress_from_mouse(scene._bar_x + scene._bar_w // 2) == pytest.approx(0.5, abs=0.01)

    def test_layout_survives_a_resize(self, scene):
        scene.sw, scene.sh = 1100, 640
        scene._rebuild_layout()

        section_bar = pygame.Rect(scene._bar_x, scene._sec_bar_y, scene._bar_w, scene._bar_h)
        assert scene._section_bar_rect.contains(section_bar)
        assert scene._dim_overlay.get_size() == (1100, 640)


class TestPanelText:
    def test_panel_labels_stay_inside_the_panel(self, scene, surface):
        """The longest drill name used to overflow the divider into the animation area."""
        render(scene, surface)
        limit = scene._panel_rect.width - scene._s(14) * 2

        for text, largest, bold in [
            ("Cooldown: Pause Arms Away", 52, True),
            ("28 spm  Tension: 5", 36, False),
            ("Section 12/21 (Cooldown)", 36, False),
        ]:
            width = scene._font_fitting(text, limit, largest, bold=bold).size(text)[0]
            assert width <= limit, f"{text!r} overflows the panel"

    def test_short_names_keep_the_large_font(self, scene):
        limit = scene._panel_rect.width - scene._s(14) * 2

        assert scene._font_fitting("REST", limit, 52, bold=True) is scene._font(52, bold=True)

    def test_ready_hint_does_not_cover_the_start_button(self, scene):
        hint = scene._font_hint.render("Space / Enter to start", True, (110, 110, 110))
        hint_rect = hint.get_rect(centerx=scene._anim_rect.centerx, top=scene._ready_btn.rect.bottom + scene._s(10))

        assert not hint_rect.colliderect(scene._ready_btn.rect)

    def test_section_list_sits_above_the_transport_buttons(self, scene):
        assert scene._section_list_rect.bottom <= scene._btn_play.rect.top

    @pytest.mark.parametrize("size", [(410, 200), (820, 422)])
    def test_real_labels_fit_the_panel_without_relying_on_clipping(self, scene, size):
        """Auto-fitting alone should keep every label the app can produce inside the panel."""
        scene.sw, scene.sh = size
        scene._rebuild_layout()
        limit = scene._panel_rect.width - scene._s(14) * 2
        widest = max(
            (f"{t.label}: {d.display_label}" for d in DrillType for t in (SectionType.warmup, SectionType.cooldown)),
            key=len,
        )

        rendered = scene._font_fitting(widest, limit, 52, bold=True).size(widest)[0]

        assert rendered <= scene._panel_rect.width, f"{widest!r} would cross the divider"

    def test_an_over_long_label_is_clipped_at_the_panel_edge(self, scene):
        """Labels are data-driven, so the panel clips as a backstop when fitting runs out of room."""
        surface = pygame.Surface((scene.sw, scene.sh))
        surface.fill(BG_COLOR)
        absurd = "Cooldown: " + "Pause Arms Away " * 8

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(type(scene._player), "current_drill_type", property(lambda _self: DrillType.pause_arms_away))
            mp.setattr(DrillType, "display_label", property(lambda _self: absurd))
            scene._draw_panel(surface, DRILL_PROFILES[DrillType.pause_arms_away])

        divider_x = scene._panel_rect.right
        beyond = [surface.get_at((divider_x + 2, y))[:3] for y in range(scene.sh)]

        assert set(beyond) == {BG_COLOR}, "panel content bled past the divider into the animation area"


class TestReadyPrompt:
    def test_starts_on_the_ready_screen_not_playing(self, scene):
        assert scene._ready_prompt
        assert scene._player.state is PlayerState.stopped

    def test_play_button_shows_play_not_pause(self, scene, surface):
        render(scene, surface)

        assert scene._btn_play.label == ">"

    def test_transport_buttons_are_live_on_the_ready_screen(self, scene):
        """They are drawn, so they must work rather than look dead."""
        scene.handle_event(click_at(scene._btn_next.rect.center))

        assert scene._player.section_idx == 1

    def test_pressing_play_starts_the_workout(self, scene):
        scene.handle_event(click_at(scene._btn_play.rect.center))

        assert not scene._ready_prompt
        assert scene._player.state is PlayerState.playing

    def test_space_starts_the_workout(self, scene):
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

        assert not scene._ready_prompt


class TestScrubbing:
    def test_dragging_pauses_and_releasing_resumes(self, scene):
        scene._start_workout()
        scene._player.update(5.0)

        scene.handle_event(click_at((scene._bar_x + 10, scene._total_bar_y)))
        assert scene._player.state is PlayerState.paused, "scrubbing should pause while dragging"

        scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(scene._bar_x + scene._bar_w // 2, 0)))
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0)))

        assert scene._player.state is PlayerState.playing, "playback must resume after the drag"
        assert scene._player.total_elapsed == pytest.approx(scene._player.total_duration / 2, rel=0.02)

    def test_dragging_while_paused_stays_paused(self, scene):
        scene._start_workout()
        scene._player.pause()

        scene.handle_event(click_at((scene._bar_x + 10, scene._sec_bar_y)))
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0)))

        assert scene._player.state is PlayerState.paused

    def test_hovering_a_bar_previews_the_time_under_the_pointer(self, scene):
        scene._start_workout()

        scene._update_hover((scene._bar_x + int(scene._bar_w * 0.25), scene._total_bar_y))

        assert scene._hover_bar == "total"
        assert scene._preview_time == pytest.approx(scene._player.total_duration * 0.25, rel=0.02)

    def test_scrubbing_back_after_finishing_resumes_from_there(self, scene):
        """The bars stay draggable after the workout ends; resuming must not restart from zero."""
        scene._start_workout()
        scene._player.seek_total(scene._player.total_duration)
        scene._player.update(1.0)
        assert scene._player.state is PlayerState.finished

        target_x = scene._bar_x + scene._bar_w // 4
        scene.handle_event(click_at((scene._bar_x + 10, scene._total_bar_y)))
        scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(target_x, scene._total_bar_y)))
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(target_x, scene._total_bar_y)))

        assert scene._player.state is not PlayerState.finished
        assert scene._player.total_elapsed == pytest.approx(scene._player.total_duration / 4, rel=0.05)

        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

        assert scene._player.state is PlayerState.playing
        assert scene._player.total_elapsed > 0, "resuming must keep the scrubbed position"

    def test_complete_message_clears_once_scrubbed_back(self, scene, surface):
        """Showing "Workout Complete!" while sitting mid-workout would be contradictory."""
        scene._start_workout()
        scene._player.seek_total(scene._player.total_duration)
        scene._player.update(1.0)
        render(scene, surface)
        finished_pixels = pygame.image.tobytes(surface, "RGB")

        scene._player.seek_total(scene._player.total_duration / 2)
        render(scene, surface)

        assert pygame.image.tobytes(surface, "RGB") != finished_pixels
        assert scene._player.state is PlayerState.paused

    def test_hover_clears_off_the_bars(self, scene):
        scene._update_hover((scene._bar_x, scene._total_bar_y))
        scene._update_hover((scene._panel_rect.centerx, scene._panel_rect.centery))

        assert scene._hover_bar is None


class TestSectionList:
    def test_scroll_is_bounded_by_the_content(self, scene):
        scene._start_workout()
        max_scroll = scene._section_list_max_scroll()
        assert max_scroll > 0, "this workout should overflow the list"

        for _ in range(50):
            scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-1, x=0))
        assert scene._section_list_scroll <= max_scroll

    def test_scroll_resets_when_the_section_changes(self, scene):
        scene._start_workout()
        scene._section_list_scroll = 20

        scene._player.next_section()
        scene.update()

        assert scene._section_list_scroll == 0


def _to_ready(scene):
    pass  # the scene already starts on the ready screen


def _to_playing(scene):
    scene._start_workout()


def _to_paused(scene):
    scene._start_workout()
    scene._player.pause()


def _to_finished(scene):
    scene._start_workout()
    scene._player.seek_total(scene._player.total_duration)
    scene._player.update(1.0)


def _to_warning(scene):
    scene._start_workout()
    scene._player.seek_section(scene._player.current_section.duration - 3)
    scene._player.update(0.1)


def _to_confirm(scene):
    scene._start_workout()
    scene._do_stop()


def _to_dragging(scene):
    scene._start_workout()
    scene.handle_event(click_at((scene._bar_x + 10, scene._sec_bar_y)))


def _to_hovering(scene):
    scene._start_workout()
    scene._update_hover((scene._bar_x + 10, scene._total_bar_y))


def _to_rest(scene):
    scene._start_workout()
    while not scene._player.is_rest_section and scene._player.remaining_count:
        scene._player.next_section()


SCENE_STATES = {
    "ready": _to_ready,
    "playing": _to_playing,
    "paused": _to_paused,
    "finished": _to_finished,
    "warning": _to_warning,
    "confirm": _to_confirm,
    "dragging": _to_dragging,
    "hovering": _to_hovering,
    "rest": _to_rest,
}


class TestRendering:
    @pytest.mark.parametrize("state", list(SCENE_STATES))
    def test_every_state_renders_without_error(self, scene, surface, state):
        """A draw path that raises would take the whole app down mid-workout."""
        SCENE_STATES[state](scene)

        render(scene, surface)

        assert surface.get_at((0, 0))[:3] != (0, 0, 0), "the panel should have painted"

    def test_a_full_second_of_playback_renders(self, scene, surface):
        scene._start_workout()

        for _ in range(60):
            scene.manager.clock.tick(60)
            render(scene, surface)

        assert scene._player.total_elapsed > 0


class TestAudioFallback:
    def test_missing_audio_device_does_not_break_playback(self, scene, monkeypatch):
        """No sound card must mean a silent pacer, not a crash on every beep."""
        monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
        from scenes.animation import _make_beep

        assert _make_beep(660, 150, 0.2) is None

        scene._beep_warn = None
        scene._beep_trans = None
        scene._on_warning()
        scene._on_transition()

    def test_beeps_are_cached_across_scenes(self, stub_manager):
        from scenes.animation import _make_beep

        first = _make_beep(660, 150, 0.2)
        second = _make_beep(660, 150, 0.2)

        assert first is second


def click_at(pos) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
