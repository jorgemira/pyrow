"""Tests for the stroke-position maths: ranges, catch alignment, dwells and transitions."""

from __future__ import annotations

import pygame
import pytest

from animations.base import DRILL_PROFILES, DrillProfile, get_position, is_in_pause
from animations.styles import _Skeleton, body_positions
from models.workout import DrillType

_SMOOTH = DrillProfile(1.0, 0.0, None, (0, 0, 0))
_PHASES = [i / 200 for i in range(201)]


class TestProfiles:
    def test_every_drill_has_a_profile(self):
        assert set(DRILL_PROFILES) == set(DrillType)

    @pytest.mark.parametrize("drill", list(DrillType))
    def test_profile_ranges_stay_within_the_animation_area(self, drill):
        profile = DRILL_PROFILES[drill]

        assert 0.0 < profile.range_factor <= 1.0
        assert 0.0 <= profile.offset <= 1.0
        assert profile.offset + profile.range_factor <= 1.0 + 1e-9

    @pytest.mark.parametrize("drill", list(DrillType))
    def test_colors_are_valid_rgb(self, drill):
        assert all(0 <= channel <= 255 for channel in DRILL_PROFILES[drill].color)


class TestGetPosition:
    @pytest.mark.parametrize("drill", list(DrillType))
    def test_position_starts_at_the_drills_offset(self, drill):
        """Phase 0 is the catch: the figure sits at the bottom of the drill's range."""
        profile = DRILL_PROFILES[drill]

        assert get_position(0.0, profile) == pytest.approx(profile.offset)

    @pytest.mark.parametrize("drill", list(DrillType))
    def test_position_never_leaves_the_drills_range(self, drill):
        profile = DRILL_PROFILES[drill]
        low, high = profile.offset, profile.offset + profile.range_factor

        values = [get_position(p, profile) for p in _PHASES]

        assert min(values) >= low - 1e-9
        assert max(values) <= high + 1e-9

    @pytest.mark.parametrize("drill", list(DrillType))
    def test_cycle_closes_so_strokes_can_repeat_seamlessly(self, drill):
        profile = DRILL_PROFILES[drill]

        assert get_position(1.0, profile) == pytest.approx(get_position(0.0, profile), abs=1e-9)

    def test_smooth_stroke_peaks_at_mid_phase(self):
        assert get_position(0.5, _SMOOTH) == pytest.approx(1.0)

    def test_smooth_stroke_is_symmetric_about_the_finish(self):
        for phase in (0.1, 0.25, 0.4):
            assert get_position(phase, _SMOOTH) == pytest.approx(get_position(1.0 - phase, _SMOOTH))


class TestPauseMotion:
    @pytest.mark.parametrize(
        "drill",
        [d for d in DrillType if DRILL_PROFILES[d].pause_position is not None],
    )
    def test_dwell_holds_the_position_it_advertises(self, drill):
        profile = DRILL_PROFILES[drill]
        pause_at = profile.pause_position
        assert pause_at is not None
        held = {round(get_position(p, profile), 6) for p in _PHASES if is_in_pause(p, profile)}

        assert len(held) == 1, "position must not move during the dwell"
        assert held.pop() == pytest.approx(profile.offset + profile.range_factor * pause_at)

    @pytest.mark.parametrize(
        "drill",
        [d for d in DrillType if DRILL_PROFILES[d].pause_position is not None],
    )
    def test_dwell_occupies_its_share_of_the_stroke(self, drill):
        profile = DRILL_PROFILES[drill]

        dwelling = [p for p in _PHASES if is_in_pause(p, profile)]

        assert len(dwelling) / len(_PHASES) == pytest.approx(0.22, abs=0.02)

    def test_no_dwell_for_continuous_drills(self):
        assert not any(is_in_pause(p, _SMOOTH) for p in _PHASES)

    def test_drive_reaches_the_finish_before_the_recovery(self):
        profile = DRILL_PROFILES[DrillType.pause_body_over]

        assert get_position(0.34, profile) == pytest.approx(1.0)

    def test_pause_at_front_dwells_at_the_finish(self):
        profile = DRILL_PROFILES[DrillType.pause_at_front]

        assert is_in_pause(0.35, profile)
        assert get_position(0.35, profile) == pytest.approx(1.0)

    def test_pause_at_back_dwells_at_the_catch(self):
        profile = DRILL_PROFILES[DrillType.pause_at_back]

        assert is_in_pause(0.99, profile)
        assert get_position(0.99, profile) == pytest.approx(0.0)


class TestTransitions:
    def test_no_blend_when_offsets_match(self):
        profile = DRILL_PROFILES[DrillType.arms_only]

        assert get_position(0.5, profile, transition=(0.75, 0.75)) == pytest.approx(get_position(0.5, profile))

    def test_blend_starts_and_ends_at_the_given_offsets(self):
        profile = DRILL_PROFILES[DrillType.arms_only]  # range 0.25

        start = get_position(0.0, profile, transition=(0.0, 0.75))
        end = get_position(1.0, profile, transition=(0.0, 0.75))

        assert start == pytest.approx(0.0)
        assert end == pytest.approx(0.75)

    def test_blend_moves_monotonically_between_the_offsets(self):
        profile = DrillProfile(0.0001, 0.75, None, (0, 0, 0))

        offsets = [get_position(p, profile, transition=(0.0, 0.75)) for p in _PHASES]

        assert offsets == sorted(offsets)

    def test_blend_eases_in_and_out_rather_than_ramping_linearly(self):
        """A linear shift would visibly lurch at the section boundary; the offset eases instead."""
        profile = DrillProfile(0.0001, 0.75, None, (0, 0, 0))
        shift = 0.75

        covered = [get_position(p, profile, transition=(0.0, shift)) / shift for p in (0.25, 0.5, 0.75)]

        assert covered[0] == pytest.approx(0.1464, abs=1e-3), "starts gently, well behind a linear 0.25"
        assert covered[1] == pytest.approx(0.5, abs=1e-3), "halfway across at mid-stroke"
        assert covered[2] == pytest.approx(0.8536, abs=1e-3), "decelerates into the new offset"

    def test_blend_is_bounded_by_the_two_ranges(self):
        profile = DRILL_PROFILES[DrillType.arms_only]

        values = [get_position(p, profile, transition=(0.0, 0.75)) for p in _PHASES]

        assert min(values) >= 0.0 - 1e-9
        assert max(values) <= 0.75 + profile.range_factor + 1e-9


class TestBodyPositions:
    @pytest.mark.parametrize("drill", list(DrillType))
    @pytest.mark.parametrize("position", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_every_part_stays_in_range(self, drill, position):
        parts = body_positions(position, drill)

        assert set(parts) == {"legs", "body", "arms"}
        assert all(0.0 <= v <= 1.0 for v in parts.values())

    @pytest.mark.parametrize("drill", list(DrillType))
    def test_catch_is_fully_compressed_for_every_drill(self, drill):
        """Position 0.0 must mean legs compressed, body forward, arms extended."""
        parts = body_positions(0.0, drill)

        assert parts == {"legs": 0.0, "body": 0.0, "arms": 0.0}

    def test_arms_only_slides_to_the_finish_before_the_arms_move(self):
        setup = body_positions(0.7, DrillType.arms_only)
        working = body_positions(1.0, DrillType.arms_only)

        assert setup["arms"] == 0.0
        assert setup["legs"] == pytest.approx(0.7 / 0.75)
        assert working == {"legs": 1.0, "body": 0.85, "arms": 1.0}

    def test_legs_only_barely_swings_the_body_and_never_the_arms(self):
        parts = body_positions(1.0, DrillType.legs_only)

        assert parts["legs"] == 1.0
        assert parts["body"] == pytest.approx(0.15)
        assert parts["arms"] == 0.0

    def test_full_stroke_moves_everything_together(self):
        assert body_positions(0.6, DrillType.none) == {"legs": 0.6, "body": 0.6, "arms": 0.6}


class TestSkeleton:
    """The figure's joint geometry, which is computed independently of any drawing."""

    RECT = pygame.Rect(0, 0, 600, 400)

    def build(self, legs=0.0, body=0.0, arms=0.0):
        return _Skeleton.build(self.RECT, {"legs": legs, "body": body, "arms": arms})

    def test_seat_slides_towards_the_bow_as_the_legs_extend(self):
        catch = self.build(legs=0.0)
        finish = self.build(legs=1.0)

        assert finish.seat_x > catch.seat_x

    def test_seat_stays_on_the_rail(self):
        for legs in (0.0, 0.25, 0.5, 0.75, 1.0):
            skeleton = self.build(legs=legs)

            assert skeleton.rail_left <= skeleton.seat_x <= skeleton.rail_right

    def knee_bend(self, legs: float) -> float:
        """How far the knee rises above a straight foot-to-hip line, in pixels."""
        skeleton = self.build(legs=legs)
        foot, hip, knee = skeleton.foot, skeleton.hip, skeleton.knee
        along = (knee[0] - foot[0]) / (hip[0] - foot[0])
        return foot[1] + along * (hip[1] - foot[1]) - knee[1]

    def test_legs_straighten_through_the_drive(self):
        """The knee bend must shrink as the legs extend; it used to grow, bulging at the finish."""
        bends = [self.knee_bend(legs) for legs in (0.0, 0.25, 0.5, 0.75, 1.0)]

        assert bends == sorted(bends, reverse=True), f"bend should decrease, got {bends}"
        assert bends[-1] == pytest.approx(0.0, abs=1.0), "the leg is straight at the finish"
        assert bends[0] > 20, "the leg is clearly compressed at the catch"

    def test_body_swings_from_forward_to_layback(self):
        forward = self.build(body=0.0)
        layback = self.build(body=1.0)

        assert layback.shoulder[0] > forward.shoulder[0], "the torso should lean towards the stern"

    def test_hands_draw_in_towards_the_chest(self):
        extended = self.build(arms=0.0)
        finished = self.build(arms=1.0)

        assert finished.hand[0] > extended.hand[0]
        assert abs(finished.hand[0] - finished.shoulder[0]) < abs(extended.hand[0] - extended.shoulder[0])

    def test_head_sits_above_the_shoulders(self):
        skeleton = self.build(body=0.5)

        assert skeleton.head[1] < skeleton.shoulder[1]

    def test_widths_scale_with_the_drawing_area_and_never_vanish(self):
        big = _Skeleton.build(pygame.Rect(0, 0, 1600, 1200), {"legs": 0.5, "body": 0.5, "arms": 0.5})
        tiny = _Skeleton.build(pygame.Rect(0, 0, 40, 20), {"legs": 0.5, "body": 0.5, "arms": 0.5})

        assert big.limb_width > tiny.limb_width
        for skeleton in (big, tiny):
            assert skeleton.limb_width >= 3
            assert skeleton.machine_width >= 2
            assert skeleton.joint_radius >= 2
            assert skeleton.seat_w >= 6
            assert skeleton.seat_h >= 3
