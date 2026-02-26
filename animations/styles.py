from __future__ import annotations

import math
import random

import pygame

from animations.base import BaseAnimation, DrillProfile
from models.workout import DrillType


# ═════════════════════════════════════════════════════════════════════
# 1. Sliding Bar
# ═════════════════════════════════════════════════════════════════════

class SlidingBarAnimation(BaseAnimation):
    name = "Sliding Bar"

    def __init__(self):
        self._trail: list[float] = []

    def update(self, dt, position, profile):
        self._trail.append(position)
        if len(self._trail) > 18:
            self._trail.pop(0)

    def draw(self, surface, rect, position, profile, drill_type):
        r, g, b = profile.color
        bar_w = max(40, rect.height // 2)
        bar_h = max(20, int(rect.height * 0.55))
        cy = rect.centery

        # Trail
        for i, pos in enumerate(self._trail):
            alpha = int(180 * ((i + 1) / len(self._trail)) * 0.25)
            cx = rect.x + int(pos * (rect.width - bar_w)) + bar_w // 2
            trail_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            pygame.draw.rect(trail_surf, (r, g, b, alpha), (0, 0, bar_w, bar_h), border_radius=8)
            surface.blit(trail_surf, (cx - bar_w // 2, cy - bar_h // 2))

        # Glow
        cx = rect.x + int(position * (rect.width - bar_w)) + bar_w // 2
        glow_surf = pygame.Surface((bar_w + 16, bar_h + 16), pygame.SRCALPHA)
        pygame.draw.rect(glow_surf, (r, g, b, 60), (0, 0, bar_w + 16, bar_h + 16), border_radius=12)
        surface.blit(glow_surf, (cx - bar_w // 2 - 8, cy - bar_h // 2 - 8))

        # Main bar
        bar_rect = pygame.Rect(cx - bar_w // 2, cy - bar_h // 2, bar_w, bar_h)
        pygame.draw.rect(surface, profile.color, bar_rect, border_radius=8)

        # Highlight stripe
        hl = pygame.Rect(bar_rect.x + 4, bar_rect.y + 3, bar_rect.width - 8, 4)
        hl_surf = pygame.Surface((hl.width, hl.height), pygame.SRCALPHA)
        hl_surf.fill((255, 255, 255, 60))
        surface.blit(hl_surf, hl.topleft)


# ═════════════════════════════════════════════════════════════════════
# 2. Breathing Ring
# ═════════════════════════════════════════════════════════════════════

class BreathingRingAnimation(BaseAnimation):
    name = "Breathing Ring"

    def draw(self, surface, rect, position, profile, drill_type):
        cx, cy = rect.centerx, rect.centery
        max_r = min(rect.width // 2, rect.height // 2) - 6
        min_r = max(max_r // 4, 8)
        radius = int(min_r + (max_r - min_r) * position)
        r, g, b = profile.color

        # Outer glow
        gr = radius + 10
        glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (r, g, b, 35), (gr, gr), gr)
        surface.blit(glow, (cx - gr, cy - gr))

        # Filled disc (subtle)
        disc = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(disc, (r, g, b, 25), (radius, radius), radius)
        surface.blit(disc, (cx - radius, cy - radius))

        # Ring
        pygame.draw.circle(surface, profile.color, (cx, cy), radius, 3)

        # Inner accent
        inner_r = max(radius - 8, 4)
        pygame.draw.circle(surface, (r, g, b), (cx, cy), inner_r, 1)


# ═════════════════════════════════════════════════════════════════════
# 3. Wave
# ═════════════════════════════════════════════════════════════════════

class WaveAnimation(BaseAnimation):
    name = "Wave"

    def __init__(self):
        self._time = 0.0

    def update(self, dt, position, profile):
        self._time += dt

    def draw(self, surface, rect, position, profile, drill_type):
        r, g, b = profile.color
        amp = rect.height * 0.32 * max(position, 0.08)
        step = 3
        points_top: list[tuple[int, int]] = []

        for x in range(rect.x, rect.x + rect.width + step, step):
            t = (x - rect.x) / rect.width
            y = rect.centery + amp * math.sin(t * 4 * math.pi + self._time * 3.5)
            points_top.append((x, int(y)))

        # Filled region below the wave
        if len(points_top) > 1:
            fill_pts = list(points_top) + [(rect.right, rect.bottom), (rect.x, rect.bottom)]
            fill_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            local = [(p[0] - rect.x, p[1] - rect.y) for p in fill_pts]
            pygame.draw.polygon(fill_surf, (r, g, b, 35), local)
            surface.blit(fill_surf, rect.topleft)

            # Wave line
            pygame.draw.lines(surface, profile.color, False, points_top, 3)

        # Secondary wave (thinner, offset)
        pts2 = []
        for x in range(rect.x, rect.x + rect.width + step, step):
            t = (x - rect.x) / rect.width
            y = rect.centery + amp * 0.5 * math.sin(t * 4 * math.pi + self._time * 3.5 + 1.2)
            pts2.append((x, int(y)))
        if len(pts2) > 1:
            pygame.draw.lines(surface, (r, g, b), False, pts2, 1)


# ═════════════════════════════════════════════════════════════════════
# 4. Rowing Figure
# ═════════════════════════════════════════════════════════════════════

class RowingFigureAnimation(BaseAnimation):
    name = "Rowing Figure"

    def draw(self, surface, rect, position, profile, drill_type):
        # Determine which body parts move based on drill type
        parts = self._body_positions(position, drill_type)
        leg_pos = parts["legs"]
        body_pos = parts["body"]
        arm_pos = parts["arms"]

        color = profile.color
        scale = min(rect.width * 0.35, rect.height * 0.42)
        cx = rect.centerx
        cy = rect.centery

        # Foot stretcher (fixed)
        foot_x = cx - scale * 0.5
        foot_y = cy + scale * 0.35

        # Seat slides with legs
        seat_x = foot_x + scale * 0.15 + leg_pos * scale * 0.8
        seat_y = cy + scale * 0.15

        # Body rocks with body_pos
        body_angle = math.radians(-18 + body_pos * 36)
        body_len = scale * 0.5
        shoulder_x = seat_x + body_len * math.sin(body_angle)
        shoulder_y = seat_y - body_len * math.cos(body_angle)

        # Head
        head_x = shoulder_x + scale * 0.06 * math.sin(body_angle)
        head_y = shoulder_y - scale * 0.14

        # Arms: 0 = extended forward, 1 = pulled in
        handle_x = shoulder_x - (1 - arm_pos) * scale * 0.55
        handle_y = shoulder_y + scale * 0.08

        # Elbow bends as arms pull
        elbow_x = shoulder_x - (1 - arm_pos) * scale * 0.35
        elbow_y = shoulder_y + scale * 0.04 + arm_pos * scale * 0.06

        # Knee
        knee_x = (foot_x + seat_x) / 2
        knee_y = foot_y - (leg_pos * 0.15 + 0.15) * scale

        # Seat rail
        pygame.draw.line(surface, (55, 55, 55),
                         (int(foot_x + scale * 0.1), int(seat_y + 6)),
                         (int(foot_x + scale * 1.0), int(seat_y + 6)), 2)

        # Oar handle line
        oar_end_x = handle_x - scale * 0.25
        oar_end_y = handle_y - scale * 0.04
        pygame.draw.line(surface, (120, 120, 120),
                         (int(handle_x), int(handle_y)),
                         (int(oar_end_x), int(oar_end_y)), 2)

        lw = 3  # line width

        # Legs
        pygame.draw.line(surface, color, (int(foot_x), int(foot_y)),
                         (int(knee_x), int(knee_y)), lw)
        pygame.draw.line(surface, color, (int(knee_x), int(knee_y)),
                         (int(seat_x), int(seat_y)), lw)

        # Body
        pygame.draw.line(surface, color, (int(seat_x), int(seat_y)),
                         (int(shoulder_x), int(shoulder_y)), lw)

        # Arms
        pygame.draw.line(surface, color, (int(shoulder_x), int(shoulder_y)),
                         (int(elbow_x), int(elbow_y)), lw)
        pygame.draw.line(surface, color, (int(elbow_x), int(elbow_y)),
                         (int(handle_x), int(handle_y)), lw)

        # Head
        pygame.draw.circle(surface, color, (int(head_x), int(head_y)),
                           max(int(scale * 0.07), 3))

        # Seat
        pygame.draw.rect(surface, (140, 140, 140),
                         (int(seat_x - 5), int(seat_y + 1), 10, 5), border_radius=2)

    @staticmethod
    def _body_positions(position, drill_type):
        if drill_type == DrillType.arms_only:
            return {"legs": 1.0, "body": 0.85, "arms": position}
        if drill_type == DrillType.arms_and_hips:
            return {"legs": 1.0, "body": 0.3 + position * 0.55, "arms": position}
        if drill_type == DrillType.hips_and_legs:
            return {"legs": position, "body": position, "arms": 0.0}
        if drill_type == DrillType.legs_only:
            return {"legs": position, "body": 0.15 * position, "arms": 0.0}
        # full stroke, pauses, mid_slide
        return {"legs": position, "body": position, "arms": position}


# ═════════════════════════════════════════════════════════════════════
# 5. Rowing Figure V2
# ═════════════════════════════════════════════════════════════════════

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


class RowingFigureV2Animation(BaseAnimation):
    name = "Rowing Figure V2"

    def __init__(self):
        self._trail: list[tuple[float, float]] = []

    def update(self, dt, position, profile):
        self._trail.append(position)
        if len(self._trail) > 12:
            self._trail.pop(0)

    def draw(self, surface, rect, position, profile, drill_type):
        parts = RowingFigureAnimation._body_positions(position, drill_type)
        leg_pos = parts["legs"]
        body_pos = parts["body"]
        arm_pos = parts["arms"]

        colors = self._part_colors(profile.color, drill_type)
        scale = rect.height * 0.7
        lw = max(int(scale * 0.065), 3)  # limb width
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
        pygame.draw.line(surface, _MACHINE_DARK,
                         (int(rail_left), int(seat_y + scale * 0.08)),
                         (int(rail_right), int(seat_y + scale * 0.08)), 3)

        # Foot plate (angled)
        fp_x = int(foot[0] - scale * 0.02)
        fp_top = int(foot[1] - scale * 0.35)
        fp_bot = int(foot[1] + scale * 0.04)
        pygame.draw.line(surface, _MACHINE_MID, (fp_x, fp_top), (fp_x, fp_bot), 3)

        # Flywheel housing
        fw_size = int(scale * 0.18)
        fw_rect = pygame.Rect(int(flywheel_cx - fw_size), int(flywheel_cy - fw_size),
                              fw_size * 2, fw_size * 2)
        pygame.draw.rect(surface, _MACHINE_DARK, fw_rect, border_radius=4)
        pygame.draw.rect(surface, _MACHINE_MID, fw_rect, 2, border_radius=4)
        # Flywheel circle
        pygame.draw.circle(surface, _MACHINE_LIGHT,
                           (int(flywheel_cx), int(flywheel_cy)), int(scale * 0.1), 2)

        # Chain from flywheel to handle
        pygame.draw.line(surface, _CHAIN_COLOR,
                         (int(flywheel_cx), int(flywheel_cy)),
                         (int(hand[0]), int(hand[1])), 2)

        # Seat (on rail)
        seat_w = max(int(scale * 0.12), 6)
        seat_h = max(int(scale * 0.05), 3)
        pygame.draw.rect(surface, _MACHINE_LIGHT,
                         (int(seat_x - seat_w // 2), int(seat_y + 1),
                          seat_w, seat_h), border_radius=2)

        # ── Seat trail (motion ghost) ────────────────────────────
        for i, trail_pos in enumerate(self._trail):
            alpha_frac = (i + 1) / (len(self._trail) + 1) * 0.3
            t_parts = RowingFigureAnimation._body_positions(trail_pos, drill_type)
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
        pygame.draw.rect(surface, _MACHINE_LIGHT,
                         (int(hand[0] - grip_w // 2), int(hand[1] - grip_h // 2),
                          grip_w, grip_h), border_radius=1)

        # Head
        head_r = max(int(scale * 0.075), 4)
        pygame.draw.circle(surface, colors["body"], (int(head[0]), int(head[1])), head_r)
        # Head highlight
        pygame.draw.circle(surface, _bright(colors["body"], 50),
                           (int(head[0]), int(head[1])), head_r, 1)

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


# ═════════════════════════════════════════════════════════════════════
# 6. Color Pulse
# ═════════════════════════════════════════════════════════════════════

class ColorPulseAnimation(BaseAnimation):
    name = "Color Pulse"

    def __init__(self):
        self._particles: list[dict] = []

    def update(self, dt, position, profile):
        # Spawn sparks during drive phase
        if position > 0.25 and len(self._particles) < 30:
            if random.random() < 0.4:
                self._particles.append({
                    "x": 0.4 + random.random() * 0.2,
                    "y": 0.2 + random.random() * 0.6,
                    "vx": random.uniform(-0.2, 0.2),
                    "vy": random.uniform(-0.6, -0.1),
                    "life": 1.0,
                })

        for p in self._particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["life"] -= dt * 1.0
        self._particles = [p for p in self._particles if p["life"] > 0]

    def draw(self, surface, rect, position, profile, drill_type):
        r, g, b = profile.color
        intensity = max(position, 0.05)

        # Background pulse
        bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        bg.fill((r, g, b, int(intensity * 90)))
        surface.blit(bg, rect.topleft)

        # Centre glow
        glow_r = int(rect.height * (0.4 + position * 0.6))
        glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (r, g, b, int(70 * intensity)), (glow_r, glow_r), glow_r)
        surface.blit(glow, (rect.centerx - glow_r, rect.centery - glow_r))

        # Horizontal accent line
        line_w = int(rect.width * 0.6 * intensity)
        line_x = rect.centerx - line_w // 2
        pygame.draw.line(surface, (r, g, b), (line_x, rect.centery),
                         (line_x + line_w, rect.centery), 2)

        # Particles
        for p in self._particles:
            px = rect.x + int(p["x"] * rect.width)
            py = rect.y + int(p["y"] * rect.height)
            alpha = int(p["life"] * 220)
            sz = max(int(3 * p["life"]), 1)
            spark = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(spark, (r, g, b, alpha), (sz, sz), sz)
            surface.blit(spark, (px - sz, py - sz))


# ═════════════════════════════════════════════════════════════════════
# Registry
# ═════════════════════════════════════════════════════════════════════

ANIMATION_STYLES: dict[str, type[BaseAnimation]] = {
    cls.name: cls
    for cls in [
        RowingFigureV2Animation,
        RowingFigureAnimation,
        SlidingBarAnimation,
        BreathingRingAnimation,
        WaveAnimation,
        ColorPulseAnimation,
    ]
}
