from __future__ import annotations

import array
import math

import pygame

from animations.base import DRILL_PROFILES, DrillProfile, get_position, is_in_pause
from animations.styles import RowingFigureV2Animation
from models.workout import DrillType, SectionType, Workout
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

        # Start in "ready" state — wait for user before playing
        self._ready_prompt = True

        # Cached per-frame state (computed in update, reused in draw)
        self._drill = self._player.current_drill_type
        self._profile = DRILL_PROFILES[self._drill]
        self._position = get_position(0.0, self._profile)

        # Animation
        self._animation = RowingFigureV2Animation()

        # Confirmation dialog state
        self._confirm_stop_active = False

        # Progress bar drag state: None | "section" | "total"
        self._dragging_bar: str | None = None
        self._was_playing_before_drag = False
        self._drag_time: float = 0.0

        # Build size-dependent resources
        self._buttons: list[_Button] = []
        self._confirm_buttons: list[_Button] = []
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
        bar_area_h = self._s(90)
        self._panel_rect = pygame.Rect(0, 0, panel_w, self.sh)
        self._anim_rect = pygame.Rect(panel_w, 0, self.sw - panel_w, self.sh - bar_area_h)
        self._bar_rect = pygame.Rect(panel_w, self.sh - bar_area_h, self.sw - panel_w, bar_area_h)

        self._build_bar_hit_rects()
        self._build_buttons()
        self._build_ready_button()
        self._build_confirm_dialog()

    # ── Progress bar interaction ─────────────────────────────────

    def _build_bar_hit_rects(self):
        """Compute clickable rects for section and total progress bars."""
        r = self._bar_rect
        s = self._s
        pad_x = s(14)
        bar_w = r.width - pad_x * 2
        x = r.x + pad_x
        hit_h = s(26)

        self._section_bar_rect = pygame.Rect(x, r.y + s(6), bar_w, hit_h)
        self._total_bar_rect = pygame.Rect(x, r.y + s(6) + s(22) + s(14), bar_w, hit_h)

    def _bar_progress_from_mouse(self, mx: int) -> float:
        """Convert mouse X to 0.0–1.0 progress within a bar."""
        r = self._bar_rect
        pad_x = self._s(14)
        bar_x = r.x + pad_x
        bar_w = r.width - pad_x * 2
        return max(0.0, min(1.0, (mx - bar_x) / bar_w))

    def _handle_bar_mousedown(self, event: pygame.event.Event):
        if event.button != 1:
            return
        pos = event.pos
        if self._section_bar_rect.collidepoint(pos):
            target = "section"
        elif self._total_bar_rect.collidepoint(pos):
            target = "total"
        else:
            return

        self._was_playing_before_drag = self._player.state == "playing"
        self._player.pause()
        self._dragging_bar = target
        self._update_drag_time(event.pos[0])

    def _handle_bar_mousemotion(self, event: pygame.event.Event):
        if self._dragging_bar:
            self._update_drag_time(event.pos[0])

    def _handle_bar_mouseup(self, event: pygame.event.Event):
        if event.button != 1 or not self._dragging_bar:
            return
        self._apply_drag_seek()
        self._dragging_bar = None

    def _update_drag_time(self, mx: int):
        progress = self._bar_progress_from_mouse(mx)
        if self._dragging_bar == "section":
            self._drag_time = progress * self._player.current_section.duration
        else:
            self._drag_time = progress * self._player.total_duration

    def _apply_drag_seek(self):
        if self._dragging_bar == "section":
            self._player.seek_section(self._drag_time)
        else:
            self._player.seek_total(self._drag_time)

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

    def _build_ready_button(self):
        ar = self._anim_rect
        bw, bh = self._s(140), self._s(40)
        self._ready_btn = _Button(
            pygame.Rect(ar.centerx - bw // 2, ar.centery + self._s(30), bw, bh),
            "Start",
            self._start_workout,
            self._font_btn,
        )

    def _start_workout(self):
        self._ready_prompt = False
        self._player.play()

    def _build_confirm_dialog(self):
        s = self._s
        dw, dh = s(260), s(120)
        dx = (self.sw - dw) // 2
        dy = (self.sh - dh) // 2
        self._confirm_rect = pygame.Rect(dx, dy, dw, dh)

        bw, bh = s(80), s(32)
        gap = s(20)
        bx = dx + (dw - bw * 2 - gap) // 2
        by = dy + dh - bh - s(16)

        self._confirm_buttons = [
            _Button(pygame.Rect(bx, by, bw, bh), "Yes", self._confirm_stop_yes, self._font_btn),
            _Button(pygame.Rect(bx + bw + gap, by, bw, bh), "No", self._confirm_stop_no, self._font_btn),
        ]

    def _toggle_play(self):
        self._player.toggle_play_pause()

    def _do_stop(self):
        if self._confirm_stop_active:
            return
        self._player.pause()
        self._confirm_stop_active = True

    def _confirm_stop_yes(self):
        from scenes.menu import MenuScene

        self._confirm_stop_active = False
        self.manager.switch_to(MenuScene(self.manager))

    def _confirm_stop_no(self):
        self._confirm_stop_active = False

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
        if event.type == pygame.WINDOWRESIZED and self.window:
            self.sw, self.sh = self.window.size
            self._rebuild_layout()
            return

        if self._ready_prompt:
            self._ready_btn.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._start_workout()
                elif event.key == pygame.K_ESCAPE:
                    self._do_stop()
            return

        if self._confirm_stop_active:
            for btn in self._confirm_buttons:
                btn.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN or event.key == pygame.K_y:
                    self._confirm_stop_yes()
                elif event.key == pygame.K_ESCAPE or event.key == pygame.K_n:
                    self._confirm_stop_no()
            return

        if self._dragging_bar:
            if event.type == pygame.MOUSEMOTION:
                self._handle_bar_mousemotion(event)
                return
            if event.type == pygame.MOUSEBUTTONUP:
                self._handle_bar_mouseup(event)
                return

        if event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_bar_mousedown(event)

        for btn in self._buttons:
            btn.handle_event(event)

        if event.type == pygame.KEYDOWN:
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
        if self._ready_prompt:
            return
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
        if self._ready_prompt:
            self._draw_ready_prompt(surface)
        else:
            self._draw_animation(surface, self._position, self._profile, self._drill)
            self._draw_warning(surface)
        self._draw_progress_bars(surface, self._profile)

        # Separator
        pygame.draw.line(surface, (55, 55, 55), (self._panel_rect.right, 0), (self._panel_rect.right, self.sh), 1)

        if self._confirm_stop_active:
            self._draw_confirm_dialog(surface)

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
        y += s(38)

        # Next section preview
        nxt = self._player.upcoming_section
        if nxt is not None:
            if nxt.section_type == SectionType.rest:
                nxt_name = "Rest"
            else:
                nxt_drills = nxt.drills
                first_drill = nxt_drills[0].drill_type if nxt_drills else DrillType.none
                nxt_drill_name = "Full Stroke" if first_drill == DrillType.none else first_drill.label
                prefix = f"{nxt.section_type.label}: " if nxt.section_type != SectionType.work else ""
                nxt_name = f"{prefix}{nxt_drill_name}"
            nxt_detail = f"{nxt_name}  {nxt.stroke_rate} spm  {nxt.duration}s"
            surface.blit(self._font_btn.render("Next:", True, (100, 100, 100)), (x, y))
            y += s(20)
            surface.blit(self._font_btn.render(nxt_detail, True, (100, 100, 100)), (x, y))
        y += s(24)

        # Stop sign (between info and buttons)
        if self._player.state == "playing" and is_in_pause(self._player.stroke_phase, profile):
            self._draw_stop_sign(surface, r.centerx, y + s(36))

        # Buttons (at bottom of panel)
        for btn in self._buttons:
            btn.draw(surface)

        # Keyboard hints
        hints = "Space  Esc  ←→  M"
        txt = self._font_hint.render(hints, True, (70, 70, 70))
        surface.blit(txt, txt.get_rect(centerx=r.centerx, bottom=r.bottom - s(8)))

    def _draw_ready_prompt(self, surface):
        r = self._anim_rect
        txt = self._font_drill.render("Ready?", True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(centerx=r.centerx, centery=r.centery - self._s(10)))
        self._ready_btn.draw(surface)
        hint = self._font_hint.render("Space / Enter to start", True, (80, 80, 80))
        surface.blit(hint, hint.get_rect(centerx=r.centerx, top=r.centery + self._s(55)))

    def _draw_animation(self, surface, position, profile, drill_type):
        self._animation.draw(surface, self._anim_rect, position, profile, drill_type)

        if self._player.state == "finished":
            self._draw_center_text(surface, "Workout Complete!", (100, 255, 100))
        elif self._player.state == "paused":
            self._draw_center_text(surface, "Paused", DIM_TEXT)

    def _draw_progress_bars(self, surface, profile):
        r = self._bar_rect
        s = self._s
        pygame.draw.rect(surface, PANEL_COLOR, r)
        pygame.draw.line(surface, (55, 55, 55), r.topleft, r.topright, 1)

        bar_h = s(6)
        br = max(1, s(3))
        pad_x = s(14)
        bar_w = r.width - pad_x * 2
        x = r.x + pad_x

        # Section bar (top)
        se = self._player.section_elapsed
        sd = self._player.current_section.duration
        sec_progress = min(se / sd, 1.0) if sd > 0 else 0

        sec_label_y = r.y + s(6)
        surface.blit(self._font_time.render(f"Section {_fmt(se)}/{_fmt(sd)}", True, DIM_TEXT), (x, sec_label_y))
        sec_bar_y = sec_label_y + s(22)
        pygame.draw.rect(surface, (55, 55, 55), (x, sec_bar_y, bar_w, bar_h), border_radius=br)
        fill_w = int(bar_w * sec_progress)
        if fill_w > 0:
            pygame.draw.rect(surface, profile.color, (x, sec_bar_y, fill_w, bar_h), border_radius=br)

        # Total bar (bottom)
        te = self._player.total_elapsed
        td = self._player.total_duration
        total_progress = min(te / td, 1.0) if td > 0 else 0

        total_label_y = sec_bar_y + s(14)
        surface.blit(self._font_time.render(f"Total {_fmt(te)}/{_fmt(td)}", True, DIM_TEXT), (x, total_label_y))
        total_bar_y = total_label_y + s(22)
        pygame.draw.rect(surface, (55, 55, 55), (x, total_bar_y, bar_w, bar_h), border_radius=br)
        total_fill_w = int(bar_w * total_progress)
        if total_fill_w > 0:
            pygame.draw.rect(surface, (80, 160, 80), (x, total_bar_y, total_fill_w, bar_h), border_radius=br)

        # Drag tooltip
        if self._dragging_bar:
            if self._dragging_bar == "section":
                drag_progress = self._drag_time / sd if sd > 0 else 0
                bar_y = sec_bar_y
            else:
                drag_progress = self._drag_time / td if td > 0 else 0
                bar_y = total_bar_y

            cursor_x = x + int(bar_w * max(0.0, min(1.0, drag_progress)))
            pygame.draw.line(surface, TEXT_COLOR, (cursor_x, bar_y - s(4)), (cursor_x, bar_y + bar_h + s(4)), 2)

            if self._dragging_bar == "total":
                tip_label = f"{_fmt(self._drag_time)} — {self._player.section_label_at(self._drag_time)}"
            else:
                tip_label = _fmt(self._drag_time)
            tip_txt = self._font_hint.render(tip_label, True, TEXT_COLOR)
            tip_w, tip_h = tip_txt.get_size()
            tip_pad = s(4)
            tip_x = min(cursor_x - tip_w // 2, x + bar_w - tip_w - tip_pad)
            tip_x = max(tip_x, x)
            tip_y = bar_y - tip_h - s(8)
            pygame.draw.rect(
                surface,
                (60, 60, 60),
                (tip_x - tip_pad, tip_y - tip_pad // 2, tip_w + tip_pad * 2, tip_h + tip_pad),
                border_radius=max(1, s(3)),
            )
            surface.blit(tip_txt, (tip_x, tip_y))

    def _draw_center_text(self, surface, text, color):
        txt = self._font_warn.render(text, True, color)
        r = self._anim_rect
        surface.blit(txt, txt.get_rect(center=r.center))

    def _draw_confirm_dialog(self, surface):
        # Dim overlay
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        surface.blit(overlay, (0, 0))

        # Dialog box
        r = self._confirm_rect
        pygame.draw.rect(surface, PANEL_COLOR, r, border_radius=self._s(8))
        pygame.draw.rect(surface, (100, 100, 100), r, width=1, border_radius=self._s(8))

        # Question text
        txt = self._font_warn.render("Stop workout?", True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(centerx=r.centerx, top=r.top + self._s(20)))

        # Buttons
        for btn in self._confirm_buttons:
            btn.draw(surface)

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
