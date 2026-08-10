from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


def format_mmss(seconds: float) -> str:
    """Format a duration as ``M:SS``."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


class Level(Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"

    @property
    def label(self) -> str:
        return self.value.capitalize()


class SectionType(Enum):
    work = "work"
    rest = "rest"
    warmup = "warmup"
    cooldown = "cooldown"

    @property
    def label(self) -> str:
        return self.value.capitalize()


class DrillType(Enum):
    none = "none"
    arms_only = "arms_only"
    arms_and_hips = "arms_and_hips"
    hips_and_legs = "hips_and_legs"
    legs_only = "legs_only"
    mid_slide = "mid_slide"
    pause_at_back = "pause_at_back"
    pause_at_front = "pause_at_front"
    pause_arms_away = "pause_arms_away"
    pause_body_over = "pause_body_over"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

    @property
    def display_label(self) -> str:
        """Name shown to the rower — the absence of a drill is a full stroke, not "None"."""
        return "Full Stroke" if self is DrillType.none else self.label


@dataclass
class DrillEntry:
    drill_type: DrillType
    count: int

    def to_dict(self) -> dict:
        return {"type": self.drill_type.value, "count": self.count}

    @classmethod
    def from_dict(cls, data: dict) -> DrillEntry:
        return cls(
            drill_type=DrillType(data["type"]),
            count=data["count"],
        )


@dataclass
class Section:
    duration: int  # seconds
    stroke_rate: int  # strokes per minute
    tension: int = 3  # machine resistance 1-8
    drills: list[DrillEntry] = field(default_factory=list)
    repeats: int = 1
    section_type: SectionType = SectionType.work
    rest_after: int = 0  # seconds of rest auto-inserted after this section

    def summary(self) -> str:
        time_str = format_mmss(self.duration)
        drill_names = ", ".join(d.drill_type.label for d in self.drills) or "No drills"
        prefix = f"[{self.section_type.label}] " if self.section_type != SectionType.work else ""
        repeat_str = f" x{self.repeats}" if self.repeats > 1 else ""
        rest_str = f" +{self.rest_after}s rest" if self.rest_after > 0 else ""
        return f"{prefix}{time_str} @ {self.stroke_rate}spm T{self.tension}{repeat_str}{rest_str} — {drill_names}"

    def to_dict(self) -> dict:
        d = {
            "duration": self.duration,
            "stroke_rate": self.stroke_rate,
            "tension": self.tension,
            "drills": [d.to_dict() for d in self.drills],
            "repeats": self.repeats,
        }
        if self.section_type != SectionType.work:
            d["section_type"] = self.section_type.value
        if self.rest_after > 0:
            d["rest_after"] = self.rest_after
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Section:
        return cls(
            duration=data["duration"],
            stroke_rate=data["stroke_rate"],
            tension=data.get("tension", 3),
            drills=[DrillEntry.from_dict(d) for d in data.get("drills", [])],
            repeats=data.get("repeats", 1),
            section_type=SectionType(data.get("section_type", "work")),
            rest_after=data.get("rest_after", 0),
        )


@dataclass
class Workout:
    name: str
    sections: list[Section] = field(default_factory=list)
    description: str = ""
    level: Level = Level.beginner

    def flatten_sections(self) -> list[Section]:
        """Expand repeats and insert rest sections for playback."""
        flat: list[Section] = []
        for sec in self.sections:
            for i in range(sec.repeats):
                flat.append(sec)
                if sec.rest_after > 0 and (i < sec.repeats - 1 or sec.repeats == 1):
                    flat.append(
                        Section(
                            duration=sec.rest_after,
                            stroke_rate=16,
                            tension=sec.tension,
                            section_type=SectionType.rest,
                        )
                    )
        return flat

    @property
    def total_duration(self) -> int:
        """Total duration in seconds including repeats and rest."""
        return sum(s.duration for s in self.flatten_sections())

    @property
    def total_duration_str(self) -> str:
        mins, secs = divmod(self.total_duration, 60)
        return format_mmss(self.total_duration) if secs else f"{mins}min"

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "sections": [s.to_dict() for s in self.sections],
        }
        if self.description:
            d["description"] = self.description
        if self.level != Level.beginner:
            d["level"] = self.level.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Workout:
        return cls(
            name=data["name"],
            sections=[Section.from_dict(s) for s in data.get("sections", [])],
            description=data.get("description", ""),
            level=Level(data.get("level", "beginner")),
        )
