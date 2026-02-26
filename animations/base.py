from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pygame

from models.workout import DrillType


@dataclass(frozen=True)
class DrillProfile:
    range_factor: float  # 0.0-1.0, portion of full animation range
    offset: float  # 0.0-1.0, where range starts
    pause_position: float | None  # None=no pause, 0.0-1.0 where to dwell
    color: tuple[int, int, int]


DRILL_PROFILES: dict[DrillType, DrillProfile] = {
    DrillType.none: DrillProfile(1.0, 0.0, None, (100, 180, 255)),
    DrillType.arms_only: DrillProfile(0.25, 0.0, None, (255, 160, 80)),
    DrillType.arms_and_hips: DrillProfile(0.5, 0.0, None, (255, 210, 80)),
    DrillType.hips_and_legs: DrillProfile(0.7, 0.3, None, (80, 230, 160)),
    DrillType.legs_only: DrillProfile(0.3, 0.7, None, (80, 255, 80)),
    DrillType.mid_slide: DrillProfile(0.6, 0.2, 0.5, (180, 130, 255)),
    DrillType.pause_at_back: DrillProfile(1.0, 0.0, 0.0, (255, 120, 120)),
    DrillType.pause_at_front: DrillProfile(1.0, 0.0, 1.0, (120, 160, 255)),
    DrillType.pause_arms_away: DrillProfile(1.0, 0.0, 0.82, (255, 170, 100)),
    DrillType.pause_body_over: DrillProfile(1.0, 0.0, 0.6, (220, 140, 180)),
}

# ── Pause timing constants ───────────────────────────────────────

_DWELL = 0.22  # fraction of stroke cycle spent holding at the pause
_DRIVE = 0.34  # fraction of stroke cycle for the drive (0 → 1)


def get_position(phase: float, profile: DrillProfile, transition: tuple[float, float] | None = None) -> float:
    """Convert a stroke phase (0.0-1.0) to a position within the drill's range.

    Phase 0.0 = catch (start), drives to finish, recovers back.
    *transition* is ``(start_offset, end_offset)`` for blending on transition strokes.
    When provided and offsets differ, the effective offset is cosine-eased from start
    to end over the stroke cycle, producing a smooth positional shift.
    """
    raw = _paused_motion(phase, profile.pause_position) if profile.pause_position is not None else _smooth_motion(phase)
    if transition is not None:
        start_off, end_off = transition
        if start_off != end_off:
            blend = 0.5 * (1.0 - math.cos(phase * math.pi))
            offset = start_off + blend * (end_off - start_off)
            return offset + profile.range_factor * raw
    return profile.offset + profile.range_factor * raw


def is_in_pause(phase: float, profile: DrillProfile) -> bool:
    """Return True when the stroke phase is in the dwell (hold) portion."""
    if profile.pause_position is None:
        return False
    bounds = _pause_bounds(profile.pause_position)
    return bounds[0] <= phase < bounds[1]


def _smooth_motion(phase: float) -> float:
    """Smooth 0 → 1 → 0 using sine easing."""
    return math.sin(phase * math.pi)


def _pause_bounds(pause_at: float) -> tuple[float, float]:
    """Return (start, end) of the dwell window within the phase cycle."""
    # Drive takes _DRIVE of the cycle: phase 0 → _DRIVE maps to position 0 → 1.
    # Recovery fills the rest: _DRIVE → 1.0 maps position 1 → 0.
    # The pause happens during recovery at the point closest to pause_at.
    recovery_len = 1.0 - _DRIVE
    # How far into recovery is the pause? Position goes 1→0 during recovery,
    # so pause_at=0.8 is early in recovery (close to finish), 0.2 is late.
    if pause_at >= 0.99:
        # Pause right at finish — dwell starts immediately after drive
        start = _DRIVE
    elif pause_at <= 0.01:
        # Pause at catch — dwell is at the very end of recovery / start of cycle
        start = 1.0 - _DWELL
    else:
        # Pause during recovery: position 1→0, we want the moment position == pause_at
        frac_into_recovery = 1.0 - pause_at  # 0 = still at finish, 1 = at catch
        start = _DRIVE + frac_into_recovery * (recovery_len - _DWELL)
    return (start, start + _DWELL)


def _paused_motion(phase: float, pause_at: float) -> float:
    """General paused motion: drive 0→1, recover 1→pause_at, dwell, recover pause_at→0."""
    dwell_start, dwell_end = _pause_bounds(pause_at)

    # Phase 0 → _DRIVE : drive from 0 to 1
    if phase < _DRIVE:
        t = phase / _DRIVE
        return 0.5 * (1.0 - math.cos(t * math.pi))  # smooth 0→1

    # Phase _DRIVE → dwell_start : recover from 1 to pause_at
    if phase < dwell_start:
        seg = dwell_start - _DRIVE
        if seg <= 0:
            return pause_at
        t = (phase - _DRIVE) / seg
        return 1.0 + (pause_at - 1.0) * 0.5 * (1.0 - math.cos(t * math.pi))

    # Dwell
    if phase < dwell_end:
        return pause_at

    # Phase dwell_end → 1.0 : recover from pause_at to 0
    seg = 1.0 - dwell_end
    if seg <= 0:
        return 0.0
    t = (phase - dwell_end) / seg
    return pause_at * 0.5 * (1.0 + math.cos(t * math.pi))


class BaseAnimation(ABC):
    """Base class for visual pacer animations."""

    name: str = ""

    def update(self, dt: float, position: float, profile: DrillProfile) -> None:  # noqa: B027
        """Update internal animation state. Override if the style has trailing/particles."""

    @abstractmethod
    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        position: float,
        profile: DrillProfile,
        drill_type: DrillType,
    ) -> None:
        """Draw the animation within *rect* on *surface*."""
