from __future__ import annotations

import math

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


class RowingFigureV2Animation(BaseAnimation):
    name = "Rowing Figure V2"

    def __init__(self):
        self._trail: list[float] = []

    def update(self, dt, position, profile):
        self._trail.append(position)
        if len(self._trail) > 12:
            self._trail.pop(0)

    def draw(self, surface, rect, position, profile, drill_type):
        parts = body_positions(position, drill_type)
        leg_pos = parts["legs"]
        body_pos = parts["body"]
        arm_pos = parts["arms"]

        colors = self._part_colors(profile.color, drill_type)
        scale = rect.height * 0.7
        lw = max(int(scale * 0.065), 3)  # limb width
        mlw = max(int(scale * 0.013), 2)  # machine line width
        jw = max(lw // 2 + 1, 2)  # joint radius
        cx = rect.centerx + scale * 0.12
        cy = rect.centery

        # ── Skeleton positions ───────────────────────────────────
        foot = (cx - scale * 0.52, cy + scale * 0.34)
        rail_left = foot[0] + scale * 0.05
        rail_right = foot[0] + scale * 1.15

        seat_x = foot[0] + scale * 0.12 + leg_pos * scale * 0.88
        seat_y = cy + scale * 0.14
        hip = (seat_x, seat_y)

        knee_x = (foot[0] + seat_x) / 2 + leg_pos * scale * 0.04
        knee_y = foot[1] - scale * (0.16 + leg_pos * 0.18)
        knee = (knee_x, knee_y)

        body_angle = math.radians(-20 + body_pos * 38)
        body_len = scale * 0.52
        shoulder = (
            seat_x + body_len * math.sin(body_angle),
            seat_y - body_len * math.cos(body_angle),
        )

        head = (
            shoulder[0] + scale * 0.05 * math.sin(body_angle),
            shoulder[1] - scale * 0.15,
        )

        # Hands: extended forward at catch, pulled to chest at finish
        hand = (
            shoulder[0] - (1 - arm_pos) * scale * 0.55,
            shoulder[1] + scale * 0.06,
        )

        elbow = (
            shoulder[0] - (1 - arm_pos) * scale * 0.34,
            shoulder[1] + scale * 0.02 + arm_pos * scale * 0.08,
        )

        # ── Machine ─────────────────────────────────────────────
        flywheel_cx = foot[0] - scale * 0.35
        flywheel_cy = cy - scale * 0.05

        # Rail
        pygame.draw.line(
            surface,
            _MACHINE_DARK,
            (int(rail_left), int(seat_y + scale * 0.08)),
            (int(rail_right), int(seat_y + scale * 0.08)),
            mlw,
        )

        # Foot plate (angled)
        fp_x = int(foot[0] - scale * 0.02)
        fp_top = int(foot[1] - scale * 0.35)
        fp_bot = int(foot[1] + scale * 0.04)
        pygame.draw.line(surface, _MACHINE_MID, (fp_x, fp_top), (fp_x, fp_bot), mlw)

        # Flywheel housing
        fw_size = int(scale * 0.18)
        fw_rect = pygame.Rect(int(flywheel_cx - fw_size), int(flywheel_cy - fw_size), fw_size * 2, fw_size * 2)
        pygame.draw.rect(surface, _MACHINE_DARK, fw_rect, border_radius=4)
        pygame.draw.rect(surface, _MACHINE_MID, fw_rect, mlw, border_radius=4)
        # Flywheel circle
        pygame.draw.circle(surface, _MACHINE_LIGHT, (int(flywheel_cx), int(flywheel_cy)), int(scale * 0.1), mlw)

        # Chain from flywheel to handle
        pygame.draw.line(surface, _CHAIN_COLOR, (int(flywheel_cx), int(flywheel_cy)), (int(hand[0]), int(hand[1])), mlw)

        # Seat (on rail)
        seat_w = max(int(scale * 0.12), 6)
        seat_h = max(int(scale * 0.05), 3)
        pygame.draw.rect(
            surface, _MACHINE_LIGHT, (int(seat_x - seat_w // 2), int(seat_y + 1), seat_w, seat_h), border_radius=2
        )

        # ── Seat trail (motion ghost) ────────────────────────────
        for i, trail_pos in enumerate(self._trail):
            alpha_frac = (i + 1) / (len(self._trail) + 1) * 0.3
            t_parts = body_positions(trail_pos, drill_type)
            t_seat_x = foot[0] + scale * 0.12 + t_parts["legs"] * scale * 0.88
            r, g, b = profile.color
            ghost = pygame.Surface((seat_w, seat_h), pygame.SRCALPHA)
            ghost.fill((r, g, b, int(alpha_frac * 180)))
            surface.blit(ghost, (int(t_seat_x - seat_w // 2), int(seat_y + 1)))

        # ── Shadow ───────────────────────────────────────────────
        shadow_y = int(seat_y + scale * 0.12)
        shadow_w = int(scale * 0.7)
        shadow = pygame.Surface((shadow_w, 4), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 25))
        surface.blit(shadow, (int(seat_x - shadow_w // 2), shadow_y))

        # ── Figure ───────────────────────────────────────────────
        # Legs
        _limb(surface, foot, knee, colors["legs"], lw)
        _limb(surface, knee, hip, colors["legs"], lw)

        # Torso
        _limb(surface, hip, shoulder, colors["body"], lw)

        # Arms
        _limb(surface, shoulder, elbow, colors["arms"], lw)
        _limb(surface, elbow, hand, colors["arms"], lw)

        # Joints (brighter accents)
        for pos, group in [(knee, "legs"), (hip, "body"), (shoulder, "body"), (elbow, "arms")]:
            _joint(surface, pos, _bright(colors[group], 30), jw)

        # Foot anchor
        _joint(surface, foot, colors["legs"], jw)

        # Handle grip
        grip_w = max(int(scale * 0.06), 3)
        grip_h = max(int(scale * 0.03), 2)
        pygame.draw.rect(
            surface,
            _MACHINE_LIGHT,
            (int(hand[0] - grip_w // 2), int(hand[1] - grip_h // 2), grip_w, grip_h),
            border_radius=1,
        )

        # Head
        head_r = max(int(scale * 0.075), 4)
        pygame.draw.circle(surface, colors["body"], (int(head[0]), int(head[1])), head_r)
        # Head highlight
        pygame.draw.circle(surface, _bright(colors["body"], 50), (int(head[0]), int(head[1])), head_r, 1)

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
