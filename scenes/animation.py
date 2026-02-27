from __future__ import annotations

import array
import math

import pygame

from animations.base import DRILL_PROFILES, DrillProfile, get_position, is_in_pause
from animations.styles import RowingFigureV2Animation
from models.workout import SectionType, Workout
from scenes.base import Scene
from workout_player import WorkoutPlayer

BG_COLOR = (30, 30, 30)
PANEL_COLOR = (38, 38, 38)
BTN_COLOR = (58, 58, 58)
BTN_HOVER = (78, 78, 78)
TEXT_COLOR = (220, 220, 220)
DIM_TEXT = (150, 150, 150)
WARNING_BG = (50, 40, 20)
WARNING_BORDER = (255, 200, 60)

_REST_PROFILE = DrillProfile(1.0, 0.0, None, (140, 200, 255))

# Reference size — all pixel values in draw methods are authored for this size
_REF_W = 820
_REF_H = 400


def _make_beep(freq: float, duration_ms: int, volume: float = 0.25) -> pygame.mixer.Sound:
    sample_rate, _, channels = pygame.mixer.get_init() or (44100, -16, 2)
    sample_rate = abs(sample_rate)
    n = int(sample_rate * duration_ms / 1000)
    buf = array.array("h")
    for i in range(n):
        t = i / sample_rate
        env = min(i / 300, 1.0, (n - i) / 300)
        val = int(volume * 32767 * env * math.sin(2 * math.pi * freq * t))
        for _ in range(channels):
            buf.append(val)
    return pygame.mixer.Sound(buffer=buf)


class _Button:
    """Minimal clickable button for the pygame strip."""

    def __init__(self, rect: pygame.Rect, label: str, callback, font: pygame.font.Font):
        self.rect = rect
        self.label = label
        self.callback = callback
        self.font = font
        self.hovered = False

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.callback()

    def draw(self, surface: pygame.Surface):
        color = BTN_HOVER if self.hovered else BTN_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        txt = self.font.render(self.label, True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(center=self.rect.center))


class AnimationScene(Scene):
    def __init__(self, manager, workout: Workout | None = None):
        super().__init__(manager)
        self.workout = workout

    # ── Lifecycle ────────────────────────────────────────────────

    def enter(self):
        monitor_w, monitor_h = pygame.display.get_desktop_sizes()[0]
        self.sw = min(1200, max(_REF_W, int(monitor_w * 0.55)))
        self.sh = min(700, max(_REF_H, int(monitor_h * 0.55)))
        self.window = pygame.window.Window("PyRow", size=(self.sw, self.sh))
        self.window.resizable = True
        self.window.minimum_size = (_REF_W // 2, _REF_H // 2)
        self.window.position = ((monitor_w - self.sw) // 2, 30)
        self.window.always_on_top = True

        # Sounds
        self._beep_warn = _make_beep(660, 150, 0.2)
        self._beep_trans = _make_beep(880, 200, 0.25)

        # Player
        assert self.workout is not None
        self._player = WorkoutPlayer(self.workout)
        self._player.on_warning = self._on_warning
        self._player.on_transition = self._on_transition
        self._player.play()

        # Cached per-frame state (computed in update, reused in draw)
        self._drill = self._player.current_drill_type
        self._profile = DRILL_PROFILES[self._drill]
        self._position = get_position(0.0, self._profile)

        # Animation
        self._animation = RowingFigureV2Animation()

        # Build size-dependent resources
        self._buttons: list[_Button] = []
        self._rebuild_layout()

        # Reset clock so the first frame doesn't carry stale time from the menu scene
        self.manager.clock.tick(60)

    def exit(self):
        if self.window:
            self.window.destroy()
            self.window = None

    # ── Scaling ───────────────────────────────────────────────────

    def _s(self, px: int) -> int:
        """Scale a reference pixel value to current window size."""
        return max(1, int(px * self._scale))

    def _rebuild_layout(self):
        """Recompute all size-dependent resources (fonts, rects, buttons)."""
        self._scale = min(self.sh / _REF_H, self.sw / _REF_W)

        self._font_drill = pygame.font.SysFont("", max(12, self._s(52)), bold=True)
        self._font_stats = pygame.font.SysFont("", max(12, self._s(36)))
        self._font_time = pygame.font.SysFont("", max(12, self._s(30)))
        self._font_warn = pygame.font.SysFont("", max(12, self._s(32)), bold=True)
        self._font_btn = pygame.font.SysFont("", max(12, self._s(20)))
        self._font_stop = pygame.font.SysFont("", max(12, self._s(24)), bold=True)
        self._font_hint = pygame.font.SysFont("", max(12, self._s(16)))

        panel_w = self._s(240)
        self._panel_rect = pygame.Rect(0, 0, panel_w, self.sh)
        self._anim_rect = pygame.Rect(panel_w, 0, self.sw - panel_w, self.sh)

        self._build_buttons()

    # ── Buttons ──────────────────────────────────────────────────

    def _build_buttons(self):
        r = self._panel_rect
        bw, bh = self._s(42), self._s(36)
        gap = self._s(4)
        total_w = bw * 5 + gap * 4
        sx = r.x + (r.width - total_w) // 2
        sy = r.bottom - bh - self._s(28)

        def make(i, label, cb):
            rect = pygame.Rect(sx + i * (bw + gap), sy, bw, bh)
            return _Button(rect, label, cb, self._font_btn)

        self._btn_prev = make(0, "|<", self._player.prev_section)
        self._btn_play = make(1, "||", self._toggle_play)
        self._btn_stop = make(2, "Stop", self._do_stop)
        self._btn_next = make(3, ">|", self._player.next_section)
        self._btn_mute = make(4, "Mute", self._toggle_mute)

        self._buttons = [
            self._btn_prev,
            self._btn_play,
            self._btn_stop,
            self._btn_next,
            self._btn_mute,
        ]

    def _toggle_play(self):
        self._player.toggle_play_pause()

    def _do_stop(self):
        from scenes.menu import MenuScene

        self.manager.switch_to(MenuScene(self.manager))

    def _toggle_mute(self):
        self._player.muted = not self._player.muted

    # ── Sound callbacks ──────────────────────────────────────────

    def _on_warning(self):
        if not self._player.muted:
            self._beep_warn.play()

    def _on_transition(self):
        if not self._player.muted:
            self._beep_trans.play()

    def _compute_offset_transition(self) -> tuple[float, float] | None:
        """Determine offset blending for the current stroke.

        Returns ``(start_offset, end_offset)`` when the drill offset changes
        (section boundary or drill pattern cycling), or ``None`` for normal strokes.
        """
        player = self._player
        stroke_count = player.section_stroke_count
        if stroke_count <= 0:
            return None

        stroke_num = player.current_stroke_num
        current_offset = DRILL_PROFILES[player.current_drill_type].offset

        start_offset = current_offset
        end_offset = current_offset

        is_first = stroke_num == 0
        is_last = stroke_num >= stroke_count - 1

        if is_first:
            start_offset = 0.0
        else:
            prev_offset = DRILL_PROFILES[player.drill_at_stroke(stroke_num - 1)].offset
            if prev_offset != current_offset:
                start_offset = prev_offset

        if is_last:
            end_offset = 0.0

        if start_offset == current_offset and end_offset == current_offset:
            return None

        return (start_offset, end_offset)

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event):
        for btn in self._buttons:
            btn.handle_event(event)

        if event.type == pygame.WINDOWRESIZED and self.window:
            self.sw, self.sh = self.window.size
            self._rebuild_layout()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._do_stop()
            elif event.key == pygame.K_SPACE:
                self._toggle_play()
            elif event.key == pygame.K_LEFT:
                self._player.prev_section()
            elif event.key == pygame.K_RIGHT:
                self._player.next_section()
            elif event.key == pygame.K_m:
                self._toggle_mute()

    # ── Update ───────────────────────────────────────────────────

    def update(self):
        dt = min(self.manager.clock.get_time() / 1000.0, 0.1)
        self._player.update(dt)

        # Update button labels
        if self._player.state == "playing":
            self._btn_play.label = "||"
        else:
            self._btn_play.label = ">"
        self._btn_mute.label = "Unmute" if self._player.muted else "Mute"

        # Update animation (cache drill/position for draw)
        self._drill = self._player.current_drill_type
        self._profile = _REST_PROFILE if self._player.is_rest_section else DRILL_PROFILES[self._drill]
        transition = self._compute_offset_transition()
        self._position = get_position(self._player.stroke_phase, self._profile, transition=transition)
        self._animation.update(dt, self._position, self._profile)

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, surface):
        surface.fill(BG_COLOR)

        self._draw_panel(surface, self._profile)
        self._draw_animation(surface, self._position, self._profile, self._drill)
        self._draw_warning(surface)

        # Separator
        pygame.draw.line(surface, (55, 55, 55), (self._panel_rect.right, 0), (self._panel_rect.right, self.sh), 1)

    def _draw_panel(self, surface, profile):
        r = self._panel_rect
        s = self._s
        pygame.draw.rect(surface, PANEL_COLOR, r)
        x = r.x + s(14)
        y = r.y + s(14)

        # Drill type name (big, colored) — "REST" in light blue
        sec_type = self._player.current_section.section_type
        if sec_type == SectionType.rest:
            drill_name = "REST"
            drill_color = _REST_PROFILE.color
        else:
            drill_name = self._player.current_drill_type.value.replace("_", " ").title()
            if self._player.current_drill_type == self._player.current_drill_type.none:
                drill_name = "Full Stroke"
            if sec_type in (SectionType.warmup, SectionType.cooldown):
                drill_name = f"{sec_type.label}: {drill_name}"
            drill_color = profile.color
        txt = self._font_drill.render(drill_name, True, drill_color)
        surface.blit(txt, (x, y))
        y += s(58)

        # Section / SR / Tension
        sec = self._player.current_section
        surface.blit(
            self._font_stats.render(f"{sec.stroke_rate} spm  Tension: {sec.tension}", True, TEXT_COLOR), (x, y)
        )
        y += s(40)
        surface.blit(self._font_stats.render(self._player.section_label, True, DIM_TEXT), (x, y))
        y += s(44)

        # Section time + progress bar
        se = self._player.section_elapsed
        sd = sec.duration
        surface.blit(self._font_time.render(f"Section {_fmt(se)}/{_fmt(sd)}", True, DIM_TEXT), (x, y))
        y += s(34)

        bar_w = r.width - s(28)
        bar_h = s(8)
        br = max(1, s(4))
        progress = min(se / sd, 1.0) if sd > 0 else 0
        pygame.draw.rect(surface, (55, 55, 55), (x, y, bar_w, bar_h), border_radius=br)
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            pygame.draw.rect(surface, profile.color, (x, y, fill_w, bar_h), border_radius=br)
        y += s(20)

        # Total time + progress bar
        te = self._player.total_elapsed
        td = self._player.total_duration
        surface.blit(self._font_time.render(f"Total {_fmt(te)}/{_fmt(td)}", True, DIM_TEXT), (x, y))
        y += s(34)

        total_progress = min(te / td, 1.0) if td > 0 else 0
        pygame.draw.rect(surface, (55, 55, 55), (x, y, bar_w, bar_h), border_radius=br)
        total_fill_w = int(bar_w * total_progress)
        if total_fill_w > 0:
            pygame.draw.rect(surface, (80, 160, 80), (x, y, total_fill_w, bar_h), border_radius=br)
        y += s(20)

        # Stop sign (between progress bars and buttons)
        if self._player.state == "playing" and is_in_pause(self._player.stroke_phase, profile):
            self._draw_stop_sign(surface, r.centerx, y + s(36))

        # Buttons (at bottom of panel)
        for btn in self._buttons:
            btn.draw(surface)

        # Keyboard hints
        hints = "Space  Esc  ←→  M"
        txt = self._font_hint.render(hints, True, (70, 70, 70))
        surface.blit(txt, txt.get_rect(centerx=r.centerx, bottom=r.bottom - s(8)))

    def _draw_animation(self, surface, position, profile, drill_type):
        self._animation.draw(surface, self._anim_rect, position, profile, drill_type)

        if self._player.state == "finished":
            self._draw_center_text(surface, "Workout Complete!", (100, 255, 100))
        elif self._player.state == "paused":
            self._draw_center_text(surface, "Paused", DIM_TEXT)

    def _draw_center_text(self, surface, text, color):
        txt = self._font_warn.render(text, True, color)
        r = self._anim_rect
        surface.blit(txt, txt.get_rect(center=r.center))

    def _draw_stop_sign(self, surface, cx, cy):
        size = self._s(30)

        # Red octagon
        points = []
        for i in range(8):
            angle = math.pi / 8 + i * math.pi / 4
            points.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
        pygame.draw.polygon(surface, (190, 30, 30), points)
        pygame.draw.polygon(surface, (240, 60, 60), points, 2)

        # "HOLD" text
        txt = self._font_stop.render("HOLD", True, (255, 255, 255))
        surface.blit(txt, txt.get_rect(center=(cx, cy)))

    def _draw_warning(self, surface):
        if not self._player.warning_active:
            return
        countdown = max(0, self._player.warning_countdown)
        if countdown <= 0 and self._player.state == "playing":
            return

        r = self._anim_rect
        bar_h = self._s(32)
        bar_rect = pygame.Rect(r.x, r.y, r.width, bar_h)

        bg = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
        bg.fill((*WARNING_BG, 210))
        surface.blit(bg, bar_rect.topleft)

        pygame.draw.rect(surface, WARNING_BORDER, bar_rect, 1)

        cd_int = int(math.ceil(countdown))
        msg = f"{self._player.warning_text}   {cd_int}..."
        pulse = 0.7 + 0.3 * math.sin(countdown * 4)
        c = tuple(int(v * pulse) for v in WARNING_BORDER)
        txt = self._font_warn.render(msg, True, c)
        surface.blit(txt, txt.get_rect(center=bar_rect.center))


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"
