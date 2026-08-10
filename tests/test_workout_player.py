"""Tests for WorkoutPlayer: stroke maths, drill cycling, seeking and section transitions."""

from __future__ import annotations

import pytest

from models.workout import DrillEntry, DrillType, Section, SectionType, Workout
from workout_player import PlayerState, WorkoutPlayer


def make_player(*sections: Section, name: str = "T") -> WorkoutPlayer:
    return WorkoutPlayer(Workout(name=name, sections=list(sections)))


def work(duration: int = 60, stroke_rate: int = 20, **kw) -> Section:
    return Section(duration=duration, stroke_rate=stroke_rate, **kw)


def advance(player: WorkoutPlayer, seconds: float, dt: float = 1 / 60) -> None:
    """Drive the player the way the scene does: many small frames rather than one big step."""
    for _ in range(int(seconds / dt)):
        player.update(dt)


class TestConstruction:
    def test_empty_workout_is_rejected_with_a_named_error(self):
        with pytest.raises(ValueError, match='"Nothing" has no playable sections'):
            WorkoutPlayer(Workout(name="Nothing"))

    def test_zero_repeats_is_rejected(self):
        with pytest.raises(ValueError, match="repeats >= 1"):
            make_player(work(repeats=0))

    def test_starts_stopped_at_the_first_section(self):
        player = make_player(work(), work())

        assert player.state == "stopped"
        assert player.section_idx == 0
        assert player.section_elapsed == 0.0
        assert player.total_elapsed == 0.0


class TestStrokeMaths:
    def test_cycle_time_is_adjusted_to_fit_whole_strokes(self):
        # 60s at 20spm is exactly 20 strokes of 3s
        player = make_player(work(duration=60, stroke_rate=20))

        assert player.section_stroke_count == 20
        assert player.stroke_phase == 0.0

    def test_stroke_count_rounds_so_a_section_never_ends_mid_stroke(self):
        # 50s at 20spm is 16.67 strokes; rounds to 17 with a slightly shorter cycle
        player = make_player(work(duration=50, stroke_rate=20))

        assert player.section_stroke_count == 17
        player.play()
        player.update(50.0 - 1e-9)
        assert player.stroke_phase == pytest.approx(1.0, abs=1e-3)

    def test_phase_advances_linearly_through_a_stroke(self):
        player = make_player(work(duration=60, stroke_rate=20))
        player.play()

        player.update(1.5)  # half of a 3s cycle

        assert player.stroke_phase == pytest.approx(0.5)
        assert player.current_stroke_num == 0

    def test_stroke_num_increments_and_never_exceeds_the_count(self):
        player = make_player(work(duration=60, stroke_rate=20))
        player.play()

        player.update(3.0)
        assert player.current_stroke_num == 1

        player.seek_section(60.0)
        assert player.current_stroke_num == player.section_stroke_count - 1

    def test_degenerate_section_does_not_divide_by_zero(self):
        player = make_player(work(duration=60, stroke_rate=0))

        assert player.section_stroke_count == 0
        assert player.stroke_phase == 0.0
        assert player.current_stroke_num == 0


class TestDrillCycling:
    def test_no_drills_means_full_stroke(self):
        player = make_player(work())

        assert player.current_drill_type is DrillType.none

    def test_pattern_repeats_across_strokes(self):
        section = work(drills=[DrillEntry(DrillType.legs_only, 2), DrillEntry(DrillType.arms_only, 1)])
        player = make_player(section)

        pattern = [player.drill_at_stroke(n) for n in range(7)]

        assert pattern == [
            DrillType.legs_only,
            DrillType.legs_only,
            DrillType.arms_only,
            DrillType.legs_only,
            DrillType.legs_only,
            DrillType.arms_only,
            DrillType.legs_only,
        ]

    def test_current_drill_follows_elapsed_time(self):
        section = work(duration=60, stroke_rate=20, drills=[DrillEntry(DrillType.legs_only, 1)])
        player = make_player(section, work(drills=[DrillEntry(DrillType.arms_only, 1)]))
        player.play()

        assert player.current_drill_type is DrillType.legs_only
        player.next_section()
        assert player.current_drill_type is DrillType.arms_only

    def test_zero_count_drills_fall_back_to_full_stroke(self):
        player = make_player(work(drills=[DrillEntry(DrillType.legs_only, 0)]))

        assert player.current_drill_type is DrillType.none


class TestPlayback:
    def test_advances_to_the_next_section_carrying_the_overflow(self):
        player = make_player(work(duration=10), work(duration=10))
        player.play()

        player.update(10.5)

        assert player.section_idx == 1
        assert player.section_elapsed == pytest.approx(0.5)
        assert player.total_elapsed == pytest.approx(10.5)

    def test_finishes_on_the_last_section_and_clamps_elapsed(self):
        player = make_player(work(duration=10))
        player.play()

        player.update(10.5)

        assert player.state == "finished"
        assert player.section_elapsed == 10

    def test_transition_callback_fires_on_section_change(self):
        player = make_player(work(duration=10), work(duration=10))
        fired = []
        player.on_transition = lambda: fired.append(1)
        player.play()

        player.update(10.0)

        assert fired == [1]

    def test_update_is_a_no_op_unless_playing(self):
        player = make_player(work(duration=10))

        player.update(5.0)

        assert player.total_elapsed == 0.0

    def test_pause_then_resume_keeps_position(self):
        player = make_player(work(duration=60))
        player.play()
        player.update(10.0)

        player.pause()
        player.update(5.0)
        player.play()

        assert player.state == "playing"
        assert player.section_elapsed == pytest.approx(10.0)

    def test_toggle_from_finished_restarts_from_the_beginning(self):
        player = make_player(work(duration=10), work(duration=10))
        player.play()
        advance(player, 21.0)
        assert player.state == "finished"

        player.toggle_play_pause()

        assert player.state == "playing"
        assert player.section_idx == 0
        assert player.total_elapsed == 0.0

    def test_a_single_update_advances_at_most_one_section(self):
        """The scene clamps dt to 0.1s, so one frame can never span a whole section."""
        player = make_player(work(duration=10), work(duration=10), work(duration=10))
        player.play()

        player.update(25.0)

        assert player.section_idx == 1
        assert player.state == "playing"


class TestWarning:
    def test_fires_once_five_seconds_before_the_end(self):
        player = make_player(work(duration=10), work(duration=10))
        calls = []
        player.on_warning = lambda: calls.append(1)
        player.play()

        player.update(4.0)
        assert not player.warning_active

        player.update(1.5)  # 5.5s elapsed, 4.5s remaining
        assert player.warning_active
        assert calls == [1]

        player.update(1.0)
        assert calls == [1], "warning must not re-fire within the same section"

    def test_countdown_tracks_remaining_time(self):
        player = make_player(work(duration=10), work(duration=10))
        player.play()

        player.update(7.0)

        assert player.warning_countdown == pytest.approx(3.0)

    def test_text_describes_the_next_section(self):
        nxt = work(duration=60, stroke_rate=26, tension=6, drills=[DrillEntry(DrillType.legs_only, 1)])
        player = make_player(work(duration=10), nxt)
        player.play()

        player.update(6.0)

        assert player.warning_text == "Next: Legs Only @ 26spm T6"

    def test_text_announces_rest_sections(self):
        player = make_player(work(duration=10, rest_after=45))
        player.play()

        player.update(6.0)

        assert player.warning_text == "Rest: 45s"

    def test_text_announces_the_end_of_the_workout(self):
        player = make_player(work(duration=10))
        player.play()

        player.update(6.0)

        assert player.warning_text == "Workout ending!"

    def test_clears_when_moving_between_sections(self):
        player = make_player(work(duration=10), work(duration=60))
        player.play()
        player.update(6.0)
        assert player.warning_active

        player.next_section()

        assert not player.warning_active


class TestNavigation:
    def test_next_and_prev_move_between_sections_and_resync_total(self):
        player = make_player(work(duration=30), work(duration=40), work(duration=50))
        player.play()
        player.update(10.0)

        player.next_section()
        assert (player.section_idx, player.section_elapsed, player.total_elapsed) == (1, 0.0, 30)

        player.prev_section()
        assert (player.section_idx, player.section_elapsed, player.total_elapsed) == (0, 0.0, 0)

    def test_navigation_stops_at_the_boundaries(self):
        player = make_player(work(duration=30), work(duration=30))

        player.prev_section()
        assert player.section_idx == 0

        player.next_section()
        player.next_section()
        assert player.section_idx == 1


class TestSeeking:
    def test_seek_section_clamps_to_the_section_bounds(self):
        player = make_player(work(duration=30), work(duration=40))
        player.next_section()

        player.seek_section(999.0)
        assert player.section_elapsed == 40
        assert player.total_elapsed == 70

        player.seek_section(-5.0)
        assert player.section_elapsed == 0.0
        assert player.total_elapsed == 30

    def test_seek_total_selects_the_containing_section(self):
        player = make_player(work(duration=30), work(duration=40), work(duration=50))

        player.seek_total(45.0)

        assert player.section_idx == 1
        assert player.section_elapsed == pytest.approx(15.0)
        assert player.total_elapsed == pytest.approx(45.0)

    def test_seek_total_clamps_to_the_workout(self):
        player = make_player(work(duration=30), work(duration=40))

        player.seek_total(10_000.0)
        assert player.section_idx == 1
        assert player.total_elapsed == 70

        player.seek_total(-10.0)
        assert player.section_idx == 0
        assert player.total_elapsed == 0.0

    def test_seek_on_a_section_boundary_picks_the_later_section(self):
        player = make_player(work(duration=30), work(duration=40))

        player.seek_total(30.0)

        assert player.section_idx == 1
        assert player.section_elapsed == 0.0

    def test_resuming_after_a_seek_does_not_rewind(self):
        """Scrubbing a progress bar pauses, seeks, then resumes; position must survive."""
        player = make_player(work(duration=100), work(duration=100))
        player.play()
        player.update(10.0)

        player.pause()
        player.seek_total(150.0)
        player.play()

        assert player.state == "playing"
        assert player.section_idx == 1
        assert player.total_elapsed == pytest.approx(150.0)


class TestSeekingAfterFinishing:
    """The progress bars stay draggable after a workout ends, so seeking must leave 'finished'.

    Otherwise play() treats the resume as a fresh start and silently rewinds to zero.
    """

    def finished_player(self) -> WorkoutPlayer:
        player = make_player(work(duration=60), work(duration=60))
        player.play()
        advance(player, 125.0)
        assert player.state is PlayerState.finished
        return player

    def test_seeking_back_leaves_the_finished_state(self):
        player = self.finished_player()

        player.seek_total(30.0)

        assert player.state is PlayerState.paused

    def test_resuming_after_seeking_back_keeps_the_scrubbed_position(self):
        player = self.finished_player()

        player.seek_total(30.0)
        player.toggle_play_pause()

        assert player.state is PlayerState.playing
        assert player.total_elapsed == pytest.approx(30.0)
        assert player.section_idx == 0

    def test_seek_section_also_leaves_the_finished_state(self):
        player = self.finished_player()

        player.seek_section(10.0)

        assert player.state is PlayerState.paused
        assert player.total_elapsed == pytest.approx(70.0)

    def test_seeking_to_the_very_end_stays_finished(self):
        player = self.finished_player()

        player.seek_total(player.total_duration)

        assert player.state is PlayerState.finished

    def test_replaying_from_finished_without_seeking_still_restarts(self):
        """Pressing play on a completed workout should start it over, as before."""
        player = self.finished_player()

        player.toggle_play_pause()

        assert player.state is PlayerState.playing
        assert player.total_elapsed == 0.0


class TestLabels:
    def test_section_label_counts_from_one(self):
        player = make_player(work(), work())

        assert player.section_label == "Section 1/2"

    def test_non_work_sections_are_annotated(self):
        player = make_player(work(section_type=SectionType.warmup))

        assert player.section_label == "Section 1/1 (Warmup)"

    def test_label_at_time_matches_the_section_containing_it(self):
        player = make_player(work(duration=30), work(duration=40, section_type=SectionType.cooldown))

        assert player.section_label_at(0.0) == "Section 1/2"
        assert player.section_label_at(29.9) == "Section 1/2"
        assert player.section_label_at(30.0) == "Section 2/2 (Cooldown)"
        assert player.section_label_at(10_000.0) == "Section 2/2 (Cooldown)"


class TestPublicSectionAccess:
    def test_sections_exposes_the_flattened_list(self):
        player = make_player(work(duration=60, repeats=2, rest_after=30))

        assert [s.section_type for s in player.sections] == [
            SectionType.work,
            SectionType.rest,
            SectionType.work,
        ]

    def test_remaining_count_counts_sections_after_the_current_one(self):
        player = make_player(work(), work(), work())

        assert player.remaining_count == 2
        player.next_section()
        assert player.remaining_count == 1
        player.next_section()
        assert player.remaining_count == 0


class TestStateEnum:
    def test_states_compare_equal_to_their_names(self):
        """A str enum keeps existing comparisons and log output working."""
        player = make_player(work())

        assert player.state == PlayerState.stopped == "stopped"
        player.play()
        assert player.state == PlayerState.playing == "playing"

    def test_toggle_from_every_state_reaches_a_sensible_one(self):
        player = make_player(work(duration=10))

        player.toggle_play_pause()
        assert player.state is PlayerState.playing
        player.toggle_play_pause()
        assert player.state is PlayerState.paused
        player.toggle_play_pause()
        assert player.state is PlayerState.playing


class TestDerivedState:
    def test_total_duration_sums_the_flattened_sections(self):
        player = make_player(work(duration=60, repeats=2, rest_after=30))

        assert player.total_duration == 60 + 30 + 60

    def test_section_remaining_never_goes_negative(self):
        player = make_player(work(duration=10))
        player.play()
        player.update(10.5)

        assert player.section_remaining == 0.0

    def test_is_rest_section_tracks_generated_rest(self):
        player = make_player(work(duration=10, rest_after=20))

        assert not player.is_rest_section
        player.next_section()
        assert player.is_rest_section
