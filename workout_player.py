from __future__ import annotations

from collections.abc import Callable

from models.workout import DrillType, Section, SectionType, Workout


class WorkoutPlayer:
    """State machine for playing through a workout's sections."""

    def __init__(self, workout: Workout):
        self.workout = workout
        self._sections: list[Section] = workout.flatten_sections()

        # Pre-compute adjusted cycle times so each section has whole strokes.
        # This ensures the figure is always at catch (phase 0.0) at section boundaries.
        self._section_cycle_times: list[float] = []
        self._section_stroke_counts: list[int] = []
        for sec in self._sections:
            if sec.stroke_rate <= 0 or sec.duration <= 0:
                self._section_stroke_counts.append(0)
                self._section_cycle_times.append(0.0)
            else:
                count = max(1, round(sec.duration * sec.stroke_rate / 60))
                self._section_stroke_counts.append(count)
                self._section_cycle_times.append(sec.duration / count)

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
    def section_stroke_count(self) -> int:
        """Number of whole strokes in the current section."""
        return self._section_stroke_counts[self.section_idx]

    @property
    def current_stroke_num(self) -> int:
        """Which stroke (0-based) we're on within the current section."""
        ct = self._section_cycle_times[self.section_idx]
        if ct <= 0:
            return 0
        return min(int(self.section_elapsed / ct), self.section_stroke_count - 1)

    @property
    def stroke_phase(self) -> float:
        """0.0-1.0 representing position within one stroke cycle."""
        ct = self._section_cycle_times[self.section_idx]
        if ct <= 0:
            return 0.0
        return (self.section_elapsed % ct) / ct

    def drill_at_stroke(self, stroke_num: int) -> DrillType:
        """Return the drill type active at a given stroke number in the current section."""
        sec = self.current_section
        if not sec.drills:
            return DrillType.none
        pattern_len = sum(d.count for d in sec.drills)
        if pattern_len == 0:
            return DrillType.none
        pos = stroke_num % pattern_len
        cumulative = 0
        for drill in sec.drills:
            cumulative += drill.count
            if pos < cumulative:
                return drill.drill_type
        return sec.drills[-1].drill_type

    @property
    def current_drill_type(self) -> DrillType:
        return self.drill_at_stroke(self.current_stroke_num)

    @property
    def section_label(self) -> str:
        n = len(self._sections)
        label = f"Section {self.section_idx + 1}/{n}"
        st = self.current_section.section_type
        if st != SectionType.work:
            label += f" ({st.label})"
        return label

    @property
    def upcoming_section(self) -> Section | None:
        """Return the next section, or None if this is the last."""
        nxt = self.section_idx + 1
        if nxt < len(self._sections):
            return self._sections[nxt]
        return None

    def section_label_at(self, total_time: float) -> str:
        """Return the section label for an absolute time in the workout."""
        total_time = max(0.0, min(total_time, self.total_duration))
        accumulated = 0.0
        n = len(self._sections)
        for i, sec in enumerate(self._sections):
            if accumulated + sec.duration > total_time or i == n - 1:
                st = sec.section_type
                label = f"Section {i + 1}/{n}"
                if st != SectionType.work:
                    label += f" ({st.label})"
                return label
            accumulated += sec.duration
        return f"Section {n}/{n}"

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
            self._sync_total_elapsed()
            self._reset_warning()
            self.on_transition()

    def prev_section(self):
        if self.section_idx > 0:
            self.section_idx -= 1
            self.section_elapsed = 0.0
            self._sync_total_elapsed()
            self._reset_warning()
            self.on_transition()

    def seek_section(self, elapsed: float):
        """Seek within the current section to a specific elapsed time."""
        self.section_elapsed = max(0.0, min(elapsed, self.current_section.duration))
        self._sync_total_elapsed()
        self._reset_warning()

    def seek_total(self, total_time: float):
        """Seek to an absolute time in the workout, switching sections as needed."""
        total_time = max(0.0, min(total_time, self.total_duration))
        accumulated = 0.0
        for i, sec in enumerate(self._sections):
            if accumulated + sec.duration > total_time or i == len(self._sections) - 1:
                self.section_idx = i
                self.section_elapsed = total_time - accumulated
                break
            accumulated += sec.duration
        self._sync_total_elapsed()
        self._reset_warning()

    def _reset_warning(self):
        self.warning_active = False
        self._warning_triggered = False

    def _sync_total_elapsed(self):
        """Recompute total_elapsed from completed sections + current offset."""
        self.total_elapsed = sum(s.duration for s in self._sections[: self.section_idx]) + self.section_elapsed

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
