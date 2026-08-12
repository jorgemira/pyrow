from __future__ import annotations

import array
import math
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pygame

from animations.base import DRILL_PROFILES, DrillProfile, get_position, is_in_pause
from animations.styles import RowingFigureV2Animation
from models.workout import DrillType, SectionType, Workout, format_mmss
from scenes.base import Scene
from workout_player import PlayerState, WorkoutPlayer

BG_COLOR = (30, 30, 30)
PANEL_COLOR = (38, 38, 38)
BTN_COLOR = (58, 58, 58)
BTN_HOVER = (78, 78, 78)
TEXT_COLOR = (220, 220, 220)
DIM_TEXT = (150, 150, 150)
WARNING_BG = (50, 40, 20)
WARNING_BORDER = (255, 200, 60)

_REST_PROFILE = DrillProfile(1.0, 0.0, None, (140, 200, 255))

_ICON_FILE = Path(__file__).parent.parent / "pyrow.png"

# Which progress bar an interaction targets
type _Bar = Literal["section", "total"]

# Reference size — all pixel values in draw methods are authored for this size
_REF_W = 820
_REF_H = 400

# Smallest comfortably legible size; the scale never shrinks text below it
_MIN_FONT_PX = 12
# Absolute floor, used only when even _MIN_FONT_PX overflows a very narrow panel
_FLOOR_FONT_PX = 8


_beep_cache: dict[tuple[float, int, float], pygame.mixer.Sound] = {}


def _make_beep(freq: float, duration_ms: int, volume: float = 0.25) -> pygame.mixer.Sound | None:
    """Return a cached beep, or None when there is no usable audio device.

    Generating the samples is a slow Python loop, so results are cached for the process. A
    machine with no sound card must still be able to run the pacer, just silently.
    """
    mixer_init = pygame.mixer.get_init()
    if mixer_init is None:
        return None

    key = (freq, duration_ms, volume)
    cached = _beep_cache.get(key)
    if cached is not None:
        return cached

    sample_rate, _, channels = mixer_init
    sample_rate = abs(sample_rate)
    n = int(sample_rate * duration_ms / 1000)
    buf = array.array("h")
    for i in range(n):
        t = i / sample_rate
        env = min(i / 300, 1.0, (n - i) / 300)
        val = int(volume * 32767 * env * math.sin(2 * math.pi * freq * t))
        for _ in range(channels):
            buf.append(val)
    sound = pygame.mixer.Sound(buffer=buf)
    _beep_cache[key] = sound
    return sound


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


def _set_window_icon(window: pygame.window.Window) -> None:
    """Apply the app icon, ignoring a missing or unreadable file — an icon is not worth a crash."""
    try:
        window.set_icon(pygame.image.load(_ICON_FILE))
    except FileNotFoundError, pygame.error:
        pass


def _top_right(window: pygame.window.Window, monitor_size: tuple[int, int]) -> tuple[int, int]:
    """Return the top-right corner of the primary monitor, in desktop coordinates.

    SDL reports monitor sizes but not their origins, so the origin is derived by asking SDL to
    centre the window on the primary monitor and working backwards from where it landed. The
    primary monitor is not always at desktop x=0, so its size alone is not enough to place a
    window against its right edge.
    """
    monitor_w, monitor_h = monitor_size
    win_w, win_h = window.size
    window.position = pygame.WINDOWPOS_CENTERED
    centered_x, centered_y = window.position
    origin_x = centered_x - (monitor_w - win_w) // 2
    origin_y = centered_y - (monitor_h - win_h) // 2
    return origin_x + monitor_w - win_w, origin_y


class AnimationScene(Scene):
    """Full-screen pacer: animated stroke guidance plus transport and progress controls."""

    def __init__(self, manager, workout: Workout):
        super().__init__(manager)
        self.workout = workout

    # ── Lifecycle ────────────────────────────────────────────────

    def enter(self):
        """Create the always-on-top window and build every size-dependent resource."""
        monitor_w, monitor_h = pygame.display.get_desktop_sizes()[0]
        self.sw = min(1200, max(_REF_W, int(monitor_w * 0.55)))
        self.sh = min(700, max(_REF_H, int(monitor_h * 0.55)))
        # Created hidden so the centre-then-move in _top_right() is not visible as a jump.
        self.window = pygame.window.Window(f"PyRow — {self.workout.name}", size=(self.sw, self.sh), hidden=True)
        self.window.resizable = True
        self.window.minimum_size = (_REF_W // 2, _REF_H // 2)
        self.window.position = _top_right(self.window, (monitor_w, monitor_h))
        self.window.always_on_top = True
        _set_window_icon(self.window)

        # Sounds
        self._beep_warn = _make_beep(660, 150, 0.2)
        self._beep_trans = _make_beep(880, 200, 0.25)

        # Player
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

        # Progress bar drag state
        self._dragging_bar: _Bar | None = None
        self._hover_bar: _Bar | None = None
        self._was_playing_before_drag = False
        self._drag_time: float = 0.0
        self._preview_time: float = 0.0
        self._cursor_hand = False

        # Remaining-sections list scroll state
        self._section_list_scroll: int = 0
        self._prev_section_idx: int = -1

        # Build size-dependent resources
        self._buttons: list[_Button] = []
        self._confirm_buttons: list[_Button] = []
        self._rebuild_layout()

        self.window.show()

        # Reset clock so the first frame doesn't carry stale time from the menu scene
        self.manager.clock.tick(60)

    def exit(self):
        """Destroy the window; the scene is not reusable afterwards."""
        if self.window:
            self.window.destroy()
            self.window = None

    # ── Scaling ───────────────────────────────────────────────────

    def _s(self, px: int) -> int:
        """Scale a reference pixel value to current window size."""
        return max(1, int(px * self._scale))

    def _font_px(self, px: int, bold: bool = False) -> pygame.font.Font:
        """Build (and cache) a font at an absolute pixel size."""
        key = (px, bold)
        font = self._font_cache.get(key)
        if font is None:
            font = pygame.font.SysFont("", px, bold=bold)
            self._font_cache[key] = font
        return font

    def _font(self, size: int, bold: bool = False) -> pygame.font.Font:
        """Return a scaled font, built once per layout."""
        return self._font_px(max(_MIN_FONT_PX, self._s(size)), bold)

    def _font_fitting(self, text: str, max_w: int, largest: int, bold: bool = False) -> pygame.font.Font:
        """Return the largest font from *largest* downwards whose rendering of *text* fits *max_w*.

        Panel labels are built from drill and section names of wildly different lengths, so a
        fixed size would either overflow the panel or waste space on short names.
        """
        size = largest
        while size > _MIN_FONT_PX:
            font = self._font(size, bold)
            if font.size(text)[0] <= max_w:
                return font
            size -= max(2, size // 8)

        # On a narrow panel the scaled minimum can still overflow, and the exact width depends on
        # the font metrics SDL_ttf happens to ship. Shrink past it rather than hand back a font
        # that provably does not fit and let the caller paint over the divider.
        for px in range(_MIN_FONT_PX, _FLOOR_FONT_PX - 1, -1):
            font = self._font_px(px, bold)
            if font.size(text)[0] <= max_w:
                return font
        return self._font_px(_FLOOR_FONT_PX, bold)

    def _rebuild_layout(self):
        """Recompute all size-dependent resources (fonts, rects, buttons)."""
        self._scale = min(self.sh / _REF_H, self.sw / _REF_W)
        self._font_cache: dict[tuple[int, bool], pygame.font.Font] = {}

        self._font_time = self._font(30)
        self._font_warn = self._font(32, bold=True)
        self._font_btn = self._font(20)
        self._font_stop = self._font(24, bold=True)
        self._font_hint = self._font(16)

        panel_w = self._s(240)
        bar_area_h = self._s(90)
        self._panel_rect = pygame.Rect(0, 0, panel_w, self.sh)
        self._anim_rect = pygame.Rect(panel_w, 0, self.sw - panel_w, self.sh - bar_area_h)
        self._bar_rect = pygame.Rect(panel_w, self.sh - bar_area_h, self.sw - panel_w, bar_area_h)

        self._build_bar_layout()
        self._build_buttons()
        self._build_ready_button()
        self._build_confirm_dialog()

        # Remaining-sections list rect — from below section label to just above the buttons
        list_top = self._panel_rect.y + self._s(168)
        list_bottom = self._btn_play.rect.top - self._s(8)
        self._section_list_rect = pygame.Rect(
            self._panel_rect.x + self._s(4),
            list_top,
            self._panel_rect.width - self._s(8),
            max(0, list_bottom - list_top),
        )

        # Translucent overlays are rebuilt per layout rather than per frame.
        self._dim_overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        self._dim_overlay.fill((0, 0, 0, 140))
        self._warning_rect = pygame.Rect(self._anim_rect.x, self._anim_rect.y, self._anim_rect.width, self._s(32))
        self._warning_bg = pygame.Surface(self._warning_rect.size, pygame.SRCALPHA)
        self._warning_bg.fill((*WARNING_BG, 210))

    # ── Progress bar interaction ─────────────────────────────────

    def _build_bar_layout(self):
        """Compute progress bar geometry once; drawing and hit-testing both read it.

        Each hit rect covers its label *and* its bar, so the whole strip is grabbable and the
        two rects together leave no dead space in the bar area.
        """
        r = self._bar_rect
        s = self._s
        pad_x = s(14)
        self._bar_x = r.x + pad_x
        self._bar_w = max(1, r.width - pad_x * 2)
        self._bar_h = s(6)

        self._sec_label_y = r.y + s(6)
        self._sec_bar_y = self._sec_label_y + s(22)
        self._total_label_y = self._sec_bar_y + s(14)
        self._total_bar_y = self._total_label_y + s(22)

        split = self._total_label_y
        self._section_bar_rect = pygame.Rect(self._bar_x, r.y, self._bar_w, split - r.y)
        self._total_bar_rect = pygame.Rect(self._bar_x, split, self._bar_w, r.bottom - split)

    def _bar_progress_from_mouse(self, mx: int) -> float:
        """Convert mouse X to 0.0–1.0 progress within a bar."""
        return max(0.0, min(1.0, (mx - self._bar_x) / self._bar_w))

    def _bar_at(self, pos: tuple[int, int]) -> _Bar | None:
        """Return which progress bar *pos* falls in, or None."""
        if self._section_bar_rect.collidepoint(pos):
            return "section"
        if self._total_bar_rect.collidepoint(pos):
            return "total"
        return None

    def _bar_duration(self, bar: _Bar) -> float:
        return self._player.current_section.duration if bar == "section" else self._player.total_duration

    def _handle_bar_mousedown(self, event: pygame.event.Event):
        if event.button != 1:
            return
        target = self._bar_at(event.pos)
        if target is None:
            return

        self._was_playing_before_drag = self._player.state == PlayerState.playing
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
        if self._was_playing_before_drag:
            self._was_playing_before_drag = False
            self._player.play()

    def _update_drag_time(self, mx: int):
        assert self._dragging_bar is not None
        self._drag_time = self._bar_progress_from_mouse(mx) * self._bar_duration(self._dragging_bar)

    def _apply_drag_seek(self):
        if self._dragging_bar == "section":
            self._player.seek_section(self._drag_time)
        else:
            self._player.seek_total(self._drag_time)

    def _update_hover(self, pos: tuple[int, int]):
        """Track which bar the pointer is over so the bars can advertise that they scrub."""
        self._hover_bar = self._bar_at(pos)
        if self._hover_bar is not None:
            self._preview_time = self._bar_progress_from_mouse(pos[0]) * self._bar_duration(self._hover_bar)

    def _update_cursor(self):
        """Show a hand over anything clickable."""
        pos = pygame.mouse.get_pos()
        if self._confirm_stop_active:
            over = any(b.rect.collidepoint(pos) for b in self._confirm_buttons)
        elif self._ready_prompt:
            over = self._ready_btn.rect.collidepoint(pos) or any(b.rect.collidepoint(pos) for b in self._buttons)
        else:
            over = self._bar_at(pos) is not None or any(b.rect.collidepoint(pos) for b in self._buttons)
        if over != self._cursor_hand:
            self._cursor_hand = over
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if over else pygame.SYSTEM_CURSOR_ARROW)

    # ── Buttons ──────────────────────────────────────────────────

    def _build_buttons(self):
        r = self._panel_rect
        bw, bh = self._s(42), self._s(36)
        gap = self._s(4)
        total_w = bw * 5 + gap * 4
        sx = r.x + (r.width - total_w) // 2
        sy = r.bottom - bh - self._s(50)  # leaves room for the two hint lines below

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
        if self._ready_prompt:
            self._start_workout()
            return
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
        if self._beep_warn is not None and not self._player.muted:
            self._beep_warn.play()

    def _on_transition(self):
        if self._beep_trans is not None and not self._player.muted:
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
        """Route an event to the handler for whichever state the scene is in."""
        if event.type == pygame.WINDOWRESIZED and self.window:
            self.sw, self.sh = self.window.size
            self._rebuild_layout()
            return

        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)

        if self._ready_prompt:
            self._handle_ready_event(event)
        elif self._confirm_stop_active:
            self._handle_confirm_event(event)
        elif self._dragging_bar and self._handle_drag_event(event):
            return
        else:
            self._handle_playback_event(event)

    def _dispatch_key(self, event, bindings: dict[int, Callable[[], None]]) -> None:
        action = bindings.get(event.key) if event.type == pygame.KEYDOWN else None
        if action is not None:
            action()

    def _handle_ready_event(self, event):
        self._ready_btn.handle_event(event)
        # The transport strip stays live so it is not a row of dead-looking controls.
        for btn in self._buttons:
            btn.handle_event(event)
        self._dispatch_key(
            event,
            {
                pygame.K_RETURN: self._start_workout,
                pygame.K_SPACE: self._start_workout,
                pygame.K_ESCAPE: self._do_stop,
                pygame.K_m: self._toggle_mute,
            },
        )

    def _handle_confirm_event(self, event):
        for btn in self._confirm_buttons:
            btn.handle_event(event)
        self._dispatch_key(
            event,
            {
                pygame.K_RETURN: self._confirm_stop_yes,
                pygame.K_y: self._confirm_stop_yes,
                pygame.K_ESCAPE: self._confirm_stop_no,
                pygame.K_n: self._confirm_stop_no,
            },
        )

    def _handle_drag_event(self, event) -> bool:
        """Handle an event during a progress-bar drag. Returns True if it was consumed."""
        if event.type == pygame.MOUSEMOTION:
            self._handle_bar_mousemotion(event)
            return True
        if event.type == pygame.MOUSEBUTTONUP:
            self._handle_bar_mouseup(event)
            return True
        return False

    def _handle_playback_event(self, event):
        if event.type == pygame.MOUSEWHEEL and self._panel_rect.collidepoint(pygame.mouse.get_pos()):
            self._scroll_section_list(event.y)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self._handle_bar_mousedown(event)

        for btn in self._buttons:
            btn.handle_event(event)

        self._dispatch_key(
            event,
            {
                pygame.K_ESCAPE: self._do_stop,
                pygame.K_SPACE: self._toggle_play,
                pygame.K_LEFT: self._player.prev_section,
                pygame.K_RIGHT: self._player.next_section,
                pygame.K_m: self._toggle_mute,
            },
        )

    def _scroll_section_list(self, wheel_y: int) -> None:
        self._section_list_scroll -= wheel_y * self._s(36)
        self._section_list_scroll = max(0, min(self._section_list_scroll, self._section_list_max_scroll()))

    # ── Update ───────────────────────────────────────────────────

    def update(self):
        """Advance the player and recompute the cached drill, profile and stroke position."""
        # Button labels track state even on the ready screen, where playback has not started.
        self._btn_play.label = "||" if self._player.state == PlayerState.playing else ">"
        self._btn_mute.label = "Unmute" if self._player.muted else "Mute"
        self._update_cursor()

        if self._ready_prompt:
            return
        dt = min(self.manager.clock.get_time() / 1000.0, 0.1)
        self._player.update(dt)

        # Reset section list scroll when section changes
        if self._player.section_idx != self._prev_section_idx:
            self._section_list_scroll = 0
            self._prev_section_idx = self._player.section_idx

        # Update animation (cache drill/position for draw)
        self._drill = self._player.current_drill_type
        self._profile = _REST_PROFILE if self._player.is_rest_section else DRILL_PROFILES[self._drill]
        transition = self._compute_offset_transition()
        self._position = get_position(self._player.stroke_phase, self._profile, transition=transition)
        self._animation.update(dt, self._position, self._profile)

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, surface):
        """Paint the panel, the figure or ready prompt, the progress bars and any dialog."""
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
        pygame.draw.rect(surface, PANEL_COLOR, r)
        # Auto-fitting shrinks labels to fit, but at the minimum window size even the smallest font
        # is too wide for the panel, so clip as well to guarantee nothing crosses the divider.
        outer_clip = surface.get_clip()
        surface.set_clip(r)
        try:
            self._draw_panel_contents(surface, profile)
        finally:
            surface.set_clip(outer_clip)

    def _draw_panel_contents(self, surface, profile):
        r = self._panel_rect
        s = self._s
        x = r.x + s(14)
        y = r.y + s(14)

        # Drill type name (big, colored) — "REST" in light blue
        sec_type = self._player.current_section.section_type
        if sec_type == SectionType.rest:
            drill_name = "REST"
            drill_color = _REST_PROFILE.color
        else:
            drill_name = self._player.current_drill_type.display_label
            if sec_type in (SectionType.warmup, SectionType.cooldown):
                drill_name = f"{sec_type.label}: {drill_name}"
            drill_color = profile.color
        # Names run from "REST" to "Cooldown: Pause Arms Away", so the text is fitted to the panel.
        text_w = r.width - s(14) * 2
        txt = self._font_fitting(drill_name, text_w, 52, bold=True).render(drill_name, True, drill_color)
        surface.blit(txt, (x, y))
        y += s(58)

        # Section / SR / Tension
        sec = self._player.current_section
        stats = f"{sec.stroke_rate} spm  Tension: {sec.tension}"
        surface.blit(self._font_fitting(stats, text_w, 36).render(stats, True, TEXT_COLOR), (x, y))
        y += s(40)
        label = self._player.section_label
        surface.blit(self._font_fitting(label, text_w, 36).render(label, True, DIM_TEXT), (x, y))
        y += s(38)

        # Remaining sections header
        remaining = self._player.remaining_count
        header = f"Up next ({remaining}):" if remaining else "Last section"
        surface.blit(self._font_hint.render(header, True, (90, 90, 90)), (x, y))

        self._draw_section_list(surface)

        # Buttons (at bottom of panel)
        for btn in self._buttons:
            btn.draw(surface)

        # Keyboard hints — plain ASCII; the default font has no arrow glyphs
        hint_lines = ("Space pause · M mute", "Arrows section · Esc stop")
        bottom = r.bottom - s(8)
        for line in reversed(hint_lines):
            txt = self._font_hint.render(line, True, (85, 85, 85))
            surface.blit(txt, txt.get_rect(centerx=r.centerx, bottom=bottom))
            bottom -= txt.get_height() + s(2)

    def _draw_ready_prompt(self, surface):
        r = self._anim_rect
        btn_rect = self._ready_btn.rect
        txt = self._font(52, bold=True).render("Ready?", True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(centerx=r.centerx, bottom=btn_rect.top - self._s(16)))
        self._ready_btn.draw(surface)
        # Positioned from the button rect so the hint can never sit on top of it.
        hint = self._font_hint.render("Space / Enter to start", True, (110, 110, 110))
        surface.blit(hint, hint.get_rect(centerx=r.centerx, top=btn_rect.bottom + self._s(10)))

    def _draw_animation(self, surface, position, profile, drill_type):
        self._animation.draw(surface, self._anim_rect, position, profile, drill_type)

        if self._player.state == PlayerState.playing and is_in_pause(self._player.stroke_phase, profile):
            r = self._anim_rect
            self._draw_stop_sign(surface, r.right - self._s(44), r.y + self._s(44))

        if self._player.state == PlayerState.finished:
            self._draw_center_text(surface, "Workout Complete!", (100, 255, 100))
        elif self._player.state == PlayerState.paused:
            self._draw_center_text(surface, "Paused", DIM_TEXT)

    def _section_list_max_scroll(self) -> int:
        n = self._player.remaining_count
        return max(0, n * self._s(36) - self._section_list_rect.height)

    def _draw_section_list(self, surface: pygame.Surface):
        r = self._section_list_rect
        if r.height <= 0:
            return

        player = self._player
        sections = player.sections
        start = player.section_idx + 1
        row_h = self._s(36)
        s = self._s

        old_clip = surface.get_clip()
        surface.set_clip(r)

        for i in range(start, len(sections)):
            row_y = r.y + (i - start) * row_h - self._section_list_scroll
            if row_y + row_h < r.y:
                continue
            if row_y >= r.bottom:
                break

            sec = sections[i]

            # Section name
            if sec.section_type == SectionType.rest:
                name = "Rest"
                name_color = _REST_PROFILE.color
            else:
                first_drill = sec.drills[0].drill_type if sec.drills else DrillType.none
                name = first_drill.display_label
                if sec.section_type in (SectionType.warmup, SectionType.cooldown):
                    name = f"{sec.section_type.label}: {name}"
                name_color = (170, 170, 170)

            surface.blit(self._font_hint.render(name, True, name_color), (r.x + s(6), row_y + s(3)))

            # Stats line
            stats = f"{sec.stroke_rate}spm  T{sec.tension}  {format_mmss(sec.duration)}"
            surface.blit(self._font_hint.render(stats, True, (90, 90, 90)), (r.x + s(6), row_y + s(19)))

        surface.set_clip(old_clip)
        self._draw_section_list_scrollbar(surface, len(sections) - start, row_h)

    def _draw_section_list_scrollbar(self, surface: pygame.Surface, row_count: int, row_h: int):
        """Show a slim thumb when the list overflows, so it is clear there is more below."""
        r = self._section_list_rect
        content_h = row_count * row_h
        if content_h <= r.height:
            return

        s = self._s
        track_w = max(2, s(3))
        track_x = r.right - track_w
        pygame.draw.rect(surface, (48, 48, 48), (track_x, r.y, track_w, r.height), border_radius=track_w // 2)

        max_scroll = content_h - r.height
        thumb_h = max(s(16), int(r.height * r.height / content_h))
        thumb_y = r.y + int((r.height - thumb_h) * self._section_list_scroll / max_scroll)
        pygame.draw.rect(surface, (95, 95, 95), (track_x, thumb_y, track_w, thumb_h), border_radius=track_w // 2)

    def _draw_progress_bars(self, surface, profile):
        r = self._bar_rect
        pygame.draw.rect(surface, PANEL_COLOR, r)
        pygame.draw.line(surface, (55, 55, 55), r.topleft, r.topright, 1)

        active = self._dragging_bar or self._hover_bar

        se = self._player.section_elapsed
        sd = self._player.current_section.duration
        self._draw_one_bar(
            surface,
            label=f"Section {format_mmss(se)}/{format_mmss(sd)}",
            label_y=self._sec_label_y,
            bar_y=self._sec_bar_y,
            progress=min(se / sd, 1.0) if sd > 0 else 0.0,
            color=profile.color,
            highlighted=active == "section",
        )

        te = self._player.total_elapsed
        td = self._player.total_duration
        self._draw_one_bar(
            surface,
            label=f"Total {format_mmss(te)}/{format_mmss(td)}",
            label_y=self._total_label_y,
            bar_y=self._total_bar_y,
            progress=min(te / td, 1.0) if td > 0 else 0.0,
            color=(80, 160, 80),
            highlighted=active == "total",
        )

        if active:
            bar_y = self._sec_bar_y if active == "section" else self._total_bar_y
            time_at = self._drag_time if self._dragging_bar else self._preview_time
            duration = self._bar_duration(active)
            self._draw_scrub_marker(surface, active, bar_y, time_at, duration)

    def _draw_one_bar(self, surface, *, label, label_y, bar_y, progress, color, highlighted):
        s = self._s
        x, bar_w, bar_h = self._bar_x, self._bar_w, self._bar_h
        if highlighted:
            # Thicken the track and lift the label so it reads as grabbable.
            bar_y -= s(1)
            bar_h += s(2)
        br = max(1, s(3))

        surface.blit(self._font_time.render(label, True, TEXT_COLOR if highlighted else DIM_TEXT), (x, label_y))
        pygame.draw.rect(
            surface, (75, 75, 75) if highlighted else (55, 55, 55), (x, bar_y, bar_w, bar_h), border_radius=br
        )
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            pygame.draw.rect(surface, color, (x, bar_y, fill_w, bar_h), border_radius=br)

    def _draw_scrub_marker(self, surface, bar: _Bar, bar_y: int, time_at: float, duration: float):
        """Draw the scrub position line and its time tooltip above the bar."""
        s = self._s
        x, bar_w = self._bar_x, self._bar_w
        progress = max(0.0, min(1.0, time_at / duration if duration > 0 else 0.0))
        cursor_x = x + int(bar_w * progress)
        pygame.draw.line(surface, TEXT_COLOR, (cursor_x, bar_y - s(4)), (cursor_x, bar_y + self._bar_h + s(4)), 2)

        tip_label = format_mmss(time_at)
        if bar == "total":
            tip_label = f"{tip_label} — {self._player.section_label_at(time_at)}"
        tip_txt = self._font_hint.render(tip_label, True, TEXT_COLOR)
        tip_w, tip_h = tip_txt.get_size()
        tip_pad = s(4)
        tip_x = max(x, min(cursor_x - tip_w // 2, x + bar_w - tip_w - tip_pad))
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
        # Dim overlay — cached, since the dialog redraws every frame while it is open
        surface.blit(self._dim_overlay, (0, 0))

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
        if countdown <= 0 and self._player.state == PlayerState.playing:
            return

        bar_rect = self._warning_rect
        surface.blit(self._warning_bg, bar_rect.topleft)
        pygame.draw.rect(surface, WARNING_BORDER, bar_rect, 1)

        cd_int = int(math.ceil(countdown))
        msg = f"{self._player.warning_text}   {cd_int}..."
        pulse = 0.7 + 0.3 * math.sin(countdown * 4)
        c = tuple(int(v * pulse) for v in WARNING_BORDER)
        txt = self._font_warn.render(msg, True, c)
        surface.blit(txt, txt.get_rect(center=bar_rect.center))
