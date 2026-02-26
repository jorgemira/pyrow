from __future__ import annotations

from collections.abc import Callable

from models.workout import DrillType, Section, SectionType, Workout


class WorkoutPlayer:
    """State machine for playing through a workout's sections."""

    def __init__(self, workout: Workout):
        self.workout = workout
        self._sections: list[Section] = workout.flatten_sections()
        self.state: str = "stopped"  # stopped | playing | paused | finished
        self.section_idx: int = 0
        self.section_elapsed: float = 0.0
        self.total_elapsed: float = 0.0
        self.muted: bool = False

        # Warning state
        self.warning_active: bool = False
        self.warning_text: str = ""
        self.warning_countdown: float = 0.0
        self._warning_triggered: bool = False

        # Sound callbacks (set by the scene)
        self.on_warning: Callable[[], None] = lambda: None
        self.on_transition: Callable[[], None] = lambda: None

    # ── Properties ───────────────────────────────────────────────

    @property
    def current_section(self):
        return self._sections[self.section_idx]

    @property
    def section_remaining(self) -> float:
        return max(0.0, self.current_section.duration - self.section_elapsed)

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self._sections)

    @property
    def is_rest_section(self) -> bool:
        return self.current_section.section_type == SectionType.rest

    @property
    def stroke_phase(self) -> float:
        """0.0-1.0 representing position within one stroke cycle."""
        sr = self.current_section.stroke_rate
        if sr <= 0:
            return 0.0
        cycle_time = 60.0 / sr
        return (self.section_elapsed % cycle_time) / cycle_time

    @property
    def current_drill_type(self) -> DrillType:
        sec = self.current_section
        if not sec.drills:
            return DrillType.none
        pattern_len = sum(d.count for d in sec.drills)
        if pattern_len == 0:
            return DrillType.none
        sr = sec.stroke_rate
        if sr <= 0:
            return sec.drills[0].drill_type
        cycle_time = 60.0 / sr
        stroke_num = int(self.section_elapsed / cycle_time)
        pos = stroke_num % pattern_len
        cumulative = 0
        for drill in sec.drills:
            cumulative += drill.count
            if pos < cumulative:
                return drill.drill_type
        return sec.drills[-1].drill_type

    @property
    def section_label(self) -> str:
        n = len(self._sections)
        label = f"Section {self.section_idx + 1}/{n}"
        st = self.current_section.section_type
        if st != SectionType.work:
            label += f" ({st.label})"
        return label

    # ── Controls ─────────────────────────────────────────────────

    def play(self):
        if self.state in ("stopped", "finished"):
            self.section_idx = 0
            self.section_elapsed = 0.0
            self.total_elapsed = 0.0
            self._warning_triggered = False
            self.warning_active = False
        self.state = "playing"

    def pause(self):
        if self.state == "playing":
            self.state = "paused"

    def toggle_play_pause(self):
        if self.state == "playing":
            self.pause()
        elif self.state in ("paused", "stopped", "finished"):
            self.play()

    def stop(self):
        self.state = "stopped"
        self.section_idx = 0
        self.section_elapsed = 0.0
        self.total_elapsed = 0.0
        self.warning_active = False
        self._warning_triggered = False

    def next_section(self):
        if self.section_idx < len(self._sections) - 1:
            self.section_idx += 1
            self.section_elapsed = 0.0
            self.warning_active = False
            self._warning_triggered = False
            self.on_transition()

    def prev_section(self):
        if self.section_idx > 0:
            self.section_idx -= 1
            self.section_elapsed = 0.0
            self.warning_active = False
            self._warning_triggered = False
            self.on_transition()

    # ── Update ───────────────────────────────────────────────────

    def update(self, dt: float):
        if self.state != "playing":
            return

        self.section_elapsed += dt
        self.total_elapsed += dt

        remaining = self.section_remaining

        # Trigger 5-second warning
        if remaining <= 5.0 and not self._warning_triggered:
            self._warning_triggered = True
            self.warning_active = True
            self._build_warning_text()
            self.on_warning()

        if self.warning_active:
            self.warning_countdown = remaining

        # Section end
        if self.section_elapsed >= self.current_section.duration:
            overflow = self.section_elapsed - self.current_section.duration
            if self.section_idx < len(self._sections) - 1:
                self.section_idx += 1
                self.section_elapsed = overflow
                self.warning_active = False
                self._warning_triggered = False
                self.on_transition()
            else:
                self.state = "finished"
                self.section_elapsed = self.current_section.duration

    def _build_warning_text(self):
        next_idx = self.section_idx + 1
        if next_idx < len(self._sections):
            ns = self._sections[next_idx]
            if ns.section_type == SectionType.rest:
                self.warning_text = f"Rest: {ns.duration}s"
            else:
                prefix = f"{ns.section_type.label}: " if ns.section_type != SectionType.work else ""
                drill_name = ns.drills[0].drill_type.value.replace("_", " ").title() if ns.drills else "Full Stroke"
                self.warning_text = f"Next: {prefix}{drill_name} @ {ns.stroke_rate}spm T{ns.tension}"
        else:
            self.warning_text = "Workout ending!"
