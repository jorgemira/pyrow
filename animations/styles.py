from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from animations.base import BaseAnimation
from models.workout import DrillType

_MACHINE_DARK = (50, 50, 55)
_MACHINE_MID = (70, 70, 75)
_MACHINE_LIGHT = (100, 100, 105)
_CHAIN_COLOR = (90, 90, 95)


def _dim(color, factor=0.22):
    return tuple(max(int(c * factor), 25) for c in color)


def _bright(color, amount=40):
    return tuple(min(c + amount, 255) for c in color)


def _limb(surface, start, end, color, width):
    """Draw a limb as a thick line with round caps."""
    s = (int(start[0]), int(start[1]))
    e = (int(end[0]), int(end[1]))
    r = max(width // 2, 1)
    pygame.draw.line(surface, color, s, e, width)
    pygame.draw.circle(surface, color, s, r)
    pygame.draw.circle(surface, color, e, r)


def _joint(surface, pos, color, radius):
    pygame.draw.circle(surface, color, (int(pos[0]), int(pos[1])), radius)


def body_positions(position, drill_type):
    """Map a single position float (0.0-1.0) to per-body-part positions."""
    if drill_type == DrillType.arms_only:
        # 0.0-0.75: setup (slide from catch to finish), 0.75-1.0: arms work
        setup = min(position / 0.75, 1.0)
        arm_t = max(0.0, (position - 0.75) / 0.25)
        return {"legs": setup, "body": setup * 0.85, "arms": arm_t}
    if drill_type == DrillType.arms_and_hips:
        # 0.0-0.50: setup (slide from catch to legs-extended), 0.50-1.0: arms+hips work
        setup = min(position / 0.5, 1.0)
        active = max(0.0, (position - 0.5) / 0.5)
        return {"legs": setup, "body": setup * 0.3 + active * 0.55, "arms": active}
    if drill_type == DrillType.hips_and_legs:
        return {"legs": position, "body": position, "arms": 0.0}
    if drill_type == DrillType.legs_only:
        return {"legs": position, "body": 0.15 * position, "arms": 0.0}
    # full stroke, pauses, mid_slide
    return {"legs": position, "body": position, "arms": position}


_TRAIL_SECONDS = 0.2  # how long the seat ghost lingers, independent of frame rate
_KNEE_BEND = 0.22  # how far the knee rises above a straight leg at full compression

_Point = tuple[float, float]


@dataclass(frozen=True)
class _Skeleton:
    """Where every joint, the seat and the machine sit for one stroke position."""

    scale: float
    limb_width: int
    machine_width: int
    joint_radius: int
    foot: _Point
    knee: _Point
    hip: _Point
    shoulder: _Point
    elbow: _Point
    hand: _Point
    head: _Point
    flywheel: _Point
    seat_x: float
    seat_y: float
    seat_w: int
    seat_h: int
    rail_left: float
    rail_right: float

    @classmethod
    def build(cls, rect: pygame.Rect, parts: dict[str, float]) -> _Skeleton:
        leg_pos, body_pos, arm_pos = parts["legs"], parts["body"], parts["arms"]
        scale = rect.height * 0.7
        limb_width = max(int(scale * 0.065), 3)
        cx = rect.centerx + scale * 0.12
        cy = rect.centery

        foot = (cx - scale * 0.52, cy + scale * 0.34)
        seat_x = foot[0] + scale * 0.12 + leg_pos * scale * 0.88
        seat_y = cy + scale * 0.14

        # The knee rides above the straight foot-to-hip line, and that bend shrinks as the legs
        # extend, so the leg is sharply compressed at the catch and almost straight at the finish.
        knee_x = (foot[0] + seat_x) / 2 + leg_pos * scale * 0.04
        span = seat_x - foot[0]
        along = (knee_x - foot[0]) / span if span else 0.5
        straight_y = foot[1] + along * (seat_y - foot[1])
        knee = (knee_x, straight_y - scale * _KNEE_BEND * (1.0 - leg_pos))

        body_angle = math.radians(-20 + body_pos * 38)
        body_len = scale * 0.52
        shoulder = (
            seat_x + body_len * math.sin(body_angle),
            seat_y - body_len * math.cos(body_angle),
        )

        return cls(
            scale=scale,
            limb_width=limb_width,
            machine_width=max(int(scale * 0.013), 2),
            joint_radius=max(limb_width // 2 + 1, 2),
            foot=foot,
            knee=knee,
            hip=(seat_x, seat_y),
            shoulder=shoulder,
            # Hands: extended forward at catch, pulled to chest at finish
            elbow=(
                shoulder[0] - (1 - arm_pos) * scale * 0.34,
                shoulder[1] + scale * 0.02 + arm_pos * scale * 0.08,
            ),
            hand=(shoulder[0] - (1 - arm_pos) * scale * 0.55, shoulder[1] + scale * 0.06),
            head=(shoulder[0] + scale * 0.05 * math.sin(body_angle), shoulder[1] - scale * 0.15),
            flywheel=(foot[0] - scale * 0.35, cy - scale * 0.05),
            seat_x=seat_x,
            seat_y=seat_y,
            seat_w=max(int(scale * 0.12), 6),
            seat_h=max(int(scale * 0.05), 3),
            rail_left=foot[0] + scale * 0.05,
            rail_right=foot[0] + scale * 1.15,
        )


class RowingFigureV2Animation(BaseAnimation):
    def __init__(self):
        self._trail: list[float] = []
        self._ghost: pygame.Surface | None = None
        self._shadow: pygame.Surface | None = None

    def update(self, dt, position, profile):
        """Record the seat position so the motion trail can be drawn."""
        # Length is derived from dt so the trail looks the same at any frame rate.
        max_len = max(1, round(_TRAIL_SECONDS / dt)) if dt > 0 else 12
        self._trail.append(position)
        del self._trail[: max(0, len(self._trail) - max_len)]

    def draw(self, surface, rect, position, profile, drill_type):
        """Draw the machine, the seat trail and the rower for one stroke position."""
        skeleton = _Skeleton.build(rect, body_positions(position, drill_type))
        colors = self._part_colors(profile.color, drill_type)

        self._draw_machine(surface, skeleton)
        self._draw_trail(surface, skeleton, profile.color, drill_type)
        self._draw_shadow(surface, skeleton)
        self._draw_figure(surface, skeleton, colors)

    @staticmethod
    def _draw_machine(surface, sk: _Skeleton) -> None:
        scale, mlw = sk.scale, sk.machine_width
        rail_y = int(sk.seat_y + scale * 0.08)
        pygame.draw.line(surface, _MACHINE_DARK, (int(sk.rail_left), rail_y), (int(sk.rail_right), rail_y), mlw)

        # Foot plate (angled)
        fp_x = int(sk.foot[0] - scale * 0.02)
        pygame.draw.line(
            surface,
            _MACHINE_MID,
            (fp_x, int(sk.foot[1] - scale * 0.35)),
            (fp_x, int(sk.foot[1] + scale * 0.04)),
            mlw,
        )

        # Flywheel housing and wheel
        fw_size = int(scale * 0.18)
        fw_rect = pygame.Rect(int(sk.flywheel[0] - fw_size), int(sk.flywheel[1] - fw_size), fw_size * 2, fw_size * 2)
        pygame.draw.rect(surface, _MACHINE_DARK, fw_rect, border_radius=4)
        pygame.draw.rect(surface, _MACHINE_MID, fw_rect, mlw, border_radius=4)
        pygame.draw.circle(surface, _MACHINE_LIGHT, (int(sk.flywheel[0]), int(sk.flywheel[1])), int(scale * 0.1), mlw)

        # Chain from flywheel to handle
        pygame.draw.line(
            surface, _CHAIN_COLOR, (int(sk.flywheel[0]), int(sk.flywheel[1])), (int(sk.hand[0]), int(sk.hand[1])), mlw
        )

        # Seat (on rail)
        pygame.draw.rect(
            surface,
            _MACHINE_LIGHT,
            (int(sk.seat_x - sk.seat_w // 2), int(sk.seat_y + 1), sk.seat_w, sk.seat_h),
            border_radius=2,
        )

    def _draw_trail(self, surface, sk: _Skeleton, color, drill_type) -> None:
        """Ghost the seat's recent positions. One surface is reused for every ghost."""
        if self._ghost is None or self._ghost.get_size() != (sk.seat_w, sk.seat_h):
            self._ghost = pygame.Surface((sk.seat_w, sk.seat_h), pygame.SRCALPHA)
        r, g, b = color
        for i, trail_pos in enumerate(self._trail):
            alpha_frac = (i + 1) / (len(self._trail) + 1) * 0.3
            legs = body_positions(trail_pos, drill_type)["legs"]
            t_seat_x = sk.foot[0] + sk.scale * 0.12 + legs * sk.scale * 0.88
            self._ghost.fill((r, g, b, int(alpha_frac * 180)))
            surface.blit(self._ghost, (int(t_seat_x - sk.seat_w // 2), int(sk.seat_y + 1)))

    def _draw_shadow(self, surface, sk: _Skeleton) -> None:
        shadow_w = int(sk.scale * 0.7)
        if self._shadow is None or self._shadow.get_width() != shadow_w:
            self._shadow = pygame.Surface((shadow_w, 4), pygame.SRCALPHA)
            self._shadow.fill((0, 0, 0, 25))
        surface.blit(self._shadow, (int(sk.seat_x - shadow_w // 2), int(sk.seat_y + sk.scale * 0.12)))

    @staticmethod
    def _draw_figure(surface, sk: _Skeleton, colors) -> None:
        lw, jw, scale = sk.limb_width, sk.joint_radius, sk.scale

        _limb(surface, sk.foot, sk.knee, colors["legs"], lw)
        _limb(surface, sk.knee, sk.hip, colors["legs"], lw)
        _limb(surface, sk.hip, sk.shoulder, colors["body"], lw)
        _limb(surface, sk.shoulder, sk.elbow, colors["arms"], lw)
        _limb(surface, sk.elbow, sk.hand, colors["arms"], lw)

        # Joints (brighter accents)
        for pos, group in [(sk.knee, "legs"), (sk.hip, "body"), (sk.shoulder, "body"), (sk.elbow, "arms")]:
            _joint(surface, pos, _bright(colors[group], 30), jw)
        _joint(surface, sk.foot, colors["legs"], jw)

        # Handle grip
        grip_w = max(int(scale * 0.06), 3)
        grip_h = max(int(scale * 0.03), 2)
        pygame.draw.rect(
            surface,
            _MACHINE_LIGHT,
            (int(sk.hand[0] - grip_w // 2), int(sk.hand[1] - grip_h // 2), grip_w, grip_h),
            border_radius=1,
        )

        # Head, with a highlight ring
        head_r = max(int(scale * 0.075), 4)
        head = (int(sk.head[0]), int(sk.head[1]))
        pygame.draw.circle(surface, colors["body"], head, head_r)
        pygame.draw.circle(surface, _bright(colors["body"], 50), head, head_r, 1)

    @staticmethod
    def _part_colors(color, drill_type):
        """Return per-group colors: active parts in full color, inactive dimmed."""
        dimmed = _dim(color)
        if drill_type == DrillType.arms_only:
            return {"arms": color, "body": dimmed, "legs": dimmed}
        if drill_type == DrillType.arms_and_hips:
            return {"arms": color, "body": color, "legs": dimmed}
        if drill_type == DrillType.hips_and_legs:
            return {"arms": dimmed, "body": color, "legs": color}
        if drill_type == DrillType.legs_only:
            return {"arms": dimmed, "body": dimmed, "legs": color}
        return {"arms": color, "body": color, "legs": color}
