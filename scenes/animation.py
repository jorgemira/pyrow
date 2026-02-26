from __future__ import annotations

import array
import math

import pygame

from animations.base import DRILL_PROFILES, BaseAnimation, get_position, is_in_pause
from animations.styles import ANIMATION_STYLES
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

_FIGURE_STYLES = {"Rowing Figure", "Rowing Figure V2"}


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
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def draw(self, surface: pygame.Surface):
        color = BTN_HOVER if self.hovered else BTN_COLOR
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        txt = self.font.render(self.label, True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(center=self.rect.center))


class AnimationScene(Scene):
    def __init__(self, manager, workout: Workout | None = None,
                 animation_style: str = "Rowing Figure V2"):
        super().__init__(manager)
        self.workout = workout
        self._style_name = animation_style

    # ── Lifecycle ────────────────────────────────────────────────

    def enter(self):
        monitor_w, monitor_h = pygame.display.get_desktop_sizes()[0]
        self._is_figure = self._style_name in _FIGURE_STYLES

        if self._is_figure:
            self.sw = min(820, monitor_w)
            self.sh = min(400, monitor_h - 60)
            self.window = pygame.window.Window(
                "PyRow", size=(self.sw, self.sh),
            )
            self.window.position = ((monitor_w - self.sw) // 2, 30)
        else:
            self.sw = monitor_w
            self.sh = monitor_h // 10
            self.window = pygame.window.Window(
                "PyRow", size=(self.sw, self.sh), borderless=True,
            )
            try:
                self.window.position = (0, 0)
            except pygame.error:
                pass
        self.window.always_on_top = True

        # Fonts — large enough to read from the rowing machine
        self._font_drill = pygame.font.SysFont("", 52, bold=True)
        self._font_stats = pygame.font.SysFont("", 36)
        self._font_time = pygame.font.SysFont("", 30)
        self._font_warn = pygame.font.SysFont("", 32, bold=True)
        self._font_btn = pygame.font.SysFont("", 20)
        self._font_stop = pygame.font.SysFont("", 24, bold=True)
        self._font_hint = pygame.font.SysFont("", 16)

        # Sounds
        self._beep_warn = _make_beep(660, 150, 0.2)
        self._beep_trans = _make_beep(880, 200, 0.25)

        # Layout: left panel (info + controls) | right (animation)
        panel_w = 240
        self._panel_rect = pygame.Rect(0, 0, panel_w, self.sh)
        self._anim_rect = pygame.Rect(panel_w, 0, self.sw - panel_w, self.sh)

        # Player
        self._player = WorkoutPlayer(self.workout)
        self._player.on_warning = self._on_warning
        self._player.on_transition = self._on_transition
        self._player.play()

        # Animation style
        style_cls = ANIMATION_STYLES.get(self._style_name, list(ANIMATION_STYLES.values())[0])
        self._animation: BaseAnimation = style_cls()

        # Buttons
        self._buttons: list[_Button] = []
        self._build_buttons()

    def exit(self):
        if self.window:
            self.window.destroy()
            self.window = None

    # ── Buttons ──────────────────────────────────────────────────

    def _build_buttons(self):
        r = self._panel_rect
        bw, bh = 42, 36
        gap = 4
        total_w = bw * 5 + gap * 4
        sx = r.x + (r.width - total_w) // 2
        sy = r.bottom - bh - 28

        def make(i, label, cb):
            rect = pygame.Rect(sx + i * (bw + gap), sy, bw, bh)
            return _Button(rect, label, cb, self._font_btn)

        self._btn_prev = make(0, "|<", self._player.prev_section)
        self._btn_play = make(1, "||", self._toggle_play)
        self._btn_stop = make(2, "Stop", self._do_stop)
        self._btn_next = make(3, ">|", self._player.next_section)
        self._btn_mute = make(4, "Mute", self._toggle_mute)

        self._buttons = [
            self._btn_prev, self._btn_play, self._btn_stop,
            self._btn_next, self._btn_mute,
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

    # ── Events ───────────────────────────────────────────────────

    def handle_event(self, event):
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
        dt = self.manager.clock.get_time() / 1000.0
        self._player.update(dt)

        # Update button labels
        if self._player.state == "playing":
            self._btn_play.label = "||"
        else:
            self._btn_play.label = ">"
        self._btn_mute.label = "Unmute" if self._player.muted else "Mute"

        # Update animation
        drill = self._player.current_drill_type
        profile = DRILL_PROFILES[drill]
        position = get_position(self._player.stroke_phase, profile)
        self._animation.update(dt, position, profile)

    # ── Draw ─────────────────────────────────────────────────────

    def draw(self, surface):
        surface.fill(BG_COLOR)

        drill = self._player.current_drill_type
        profile = DRILL_PROFILES[drill]
        position = get_position(self._player.stroke_phase, profile)

        self._draw_panel(surface, profile)
        self._draw_animation(surface, position, profile, drill)
        self._draw_warning(surface)

        # Separator
        pygame.draw.line(surface, (55, 55, 55),
                         (self._panel_rect.right, 0),
                         (self._panel_rect.right, self.sh), 1)

    def _draw_panel(self, surface, profile):
        r = self._panel_rect
        pygame.draw.rect(surface, PANEL_COLOR, r)
        x = r.x + 14
        y = r.y + 14

        # Drill type name (big, colored) — or "REST" in grey
        sec_type = self._player.current_section.section_type
        if sec_type == SectionType.rest:
            drill_name = "REST"
            drill_color = DIM_TEXT
        else:
            drill_name = self._player.current_drill_type.value.replace("_", " ").title()
            if self._player.current_drill_type == self._player.current_drill_type.none:
                drill_name = "Full Stroke"
            if sec_type in (SectionType.warmup, SectionType.cooldown):
                drill_name = f"{sec_type.label}: {drill_name}"
            drill_color = profile.color
        txt = self._font_drill.render(drill_name, True, drill_color)
        surface.blit(txt, (x, y))
        y += 58

        # Section / SR / Tension
        sec = self._player.current_section
        surface.blit(self._font_stats.render(
            f"{sec.stroke_rate} spm  Tension: {sec.tension}", True, TEXT_COLOR), (x, y))
        y += 40
        surface.blit(self._font_stats.render(
            self._player.section_label, True, DIM_TEXT), (x, y))
        y += 44

        # Section time + progress bar
        se = self._player.section_elapsed
        sd = sec.duration
        surface.blit(self._font_time.render(
            f"Section {_fmt(se)}/{_fmt(sd)}", True, DIM_TEXT), (x, y))
        y += 34

        bar_w = r.width - 28
        bar_h = 8
        progress = min(se / sd, 1.0) if sd > 0 else 0
        pygame.draw.rect(surface, (55, 55, 55), (x, y, bar_w, bar_h), border_radius=4)
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            bar_color = (80, 80, 80) if sec_type == SectionType.rest else profile.color
            pygame.draw.rect(surface, bar_color, (x, y, fill_w, bar_h), border_radius=4)
        y += 20

        # Total time + progress bar
        te = self._player.total_elapsed
        td = self._player.total_duration
        surface.blit(self._font_time.render(
            f"Total {_fmt(te)}/{_fmt(td)}", True, DIM_TEXT), (x, y))
        y += 34

        total_progress = min(te / td, 1.0) if td > 0 else 0
        pygame.draw.rect(surface, (55, 55, 55), (x, y, bar_w, bar_h), border_radius=4)
        total_fill_w = int(bar_w * total_progress)
        if total_fill_w > 0:
            total_color = (80, 160, 80)
            pygame.draw.rect(surface, total_color, (x, y, total_fill_w, bar_h), border_radius=4)
        y += 20

        # Stop sign (between progress bars and buttons)
        if (self._player.state == "playing"
                and is_in_pause(self._player.stroke_phase, profile)):
            self._draw_stop_sign(surface, r.centerx, y + 36)

        # Buttons (at bottom of panel)
        for btn in self._buttons:
            btn.draw(surface)

        # Keyboard hints
        hints = "Space  Esc  ←→  M"
        txt = self._font_hint.render(hints, True, (70, 70, 70))
        surface.blit(txt, txt.get_rect(centerx=r.centerx, bottom=r.bottom - 8))

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
        size = 30

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
        bar_h = 32
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
