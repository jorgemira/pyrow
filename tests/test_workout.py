"""Tests for the workout data model: serialization, flattening and duration maths."""

from __future__ import annotations

import pytest

from models.workout import DrillEntry, DrillType, Level, Section, SectionType, Workout, format_mmss


def test_drill_labels_are_human_readable():
    assert DrillType.none.label == "None"
    assert DrillType.pause_arms_away.label == "Pause Arms Away"
    assert Level.intermediate.label == "Intermediate"
    assert SectionType.cooldown.label == "Cooldown"


@pytest.mark.parametrize("drill", list(DrillType))
def test_display_label_never_shows_none_to_the_rower(drill):
    expected = "Full Stroke" if drill is DrillType.none else drill.label

    assert drill.display_label == expected
    assert drill.display_label != "None"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00"), (5, "0:05"), (59, "0:59"), (60, "1:00"), (90, "1:30"), (600, "10:00"), (3661, "61:01")],
)
def test_mmss_formatting(seconds, expected):
    assert format_mmss(seconds) == expected


def test_mmss_truncates_fractional_seconds():
    assert format_mmss(59.9) == "0:59"


class TestSerialization:
    def test_round_trip_preserves_every_field(self):
        workout = Workout(
            name="Test",
            description="A description",
            level=Level.advanced,
            sections=[
                Section(
                    duration=300,
                    stroke_rate=24,
                    tension=5,
                    drills=[DrillEntry(DrillType.legs_only, 3), DrillEntry(DrillType.none, 1)],
                    repeats=2,
                    section_type=SectionType.warmup,
                    rest_after=60,
                )
            ],
        )

        restored = Workout.from_dict(workout.to_dict())

        assert restored == workout

    def test_defaults_are_omitted_from_json(self):
        workout = Workout(name="Plain", sections=[Section(duration=60, stroke_rate=20)])

        data = workout.to_dict()

        assert "description" not in data
        assert "level" not in data
        assert "section_type" not in data["sections"][0]
        assert "rest_after" not in data["sections"][0]

    def test_non_default_level_and_description_are_written(self):
        workout = Workout(name="X", description="hi", level=Level.intermediate)

        data = workout.to_dict()

        assert data["level"] == "intermediate"
        assert data["description"] == "hi"

    def test_missing_optional_fields_fall_back_to_defaults(self):
        workout = Workout.from_dict({"name": "Bare"})

        assert workout.sections == []
        assert workout.level is Level.beginner
        assert workout.description == ""

    def test_section_from_dict_defaults(self):
        section = Section.from_dict({"duration": 60, "stroke_rate": 20})

        assert section.tension == 3
        assert section.repeats == 1
        assert section.drills == []
        assert section.section_type is SectionType.work
        assert section.rest_after == 0

    def test_unknown_enum_value_is_rejected(self):
        with pytest.raises(ValueError):
            Section.from_dict({"duration": 60, "stroke_rate": 20, "section_type": "sprinting"})

    def test_missing_required_field_is_rejected(self):
        with pytest.raises(KeyError):
            Section.from_dict({"stroke_rate": 20})


class TestFlattenSections:
    def test_repeats_are_expanded(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=20, repeats=3)])

        assert len(workout.flatten_sections()) == 3

    def test_rest_goes_between_repeats_but_not_after_the_last(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=20, repeats=3, rest_after=30)])

        flat = workout.flatten_sections()

        assert [s.section_type for s in flat] == [
            SectionType.work,
            SectionType.rest,
            SectionType.work,
            SectionType.rest,
            SectionType.work,
        ]

    def test_single_repeat_gets_trailing_rest(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=20, repeats=1, rest_after=30)])

        flat = workout.flatten_sections()

        assert [s.section_type for s in flat] == [SectionType.work, SectionType.rest]

    def test_generated_rest_inherits_tension_and_uses_16_spm(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=28, tension=7, rest_after=45)])

        rest = workout.flatten_sections()[1]

        assert rest.duration == 45
        assert rest.stroke_rate == 16
        assert rest.tension == 7
        assert rest.drills == []

    def test_zero_repeats_yields_nothing(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=20, repeats=0)])

        assert workout.flatten_sections() == []

    def test_empty_workout_flattens_to_nothing(self):
        assert Workout(name="W").flatten_sections() == []


class TestDuration:
    def test_total_duration_counts_repeats_and_rest(self):
        workout = Workout(name="W", sections=[Section(duration=60, stroke_rate=20, repeats=3, rest_after=30)])

        assert workout.total_duration == 60 * 3 + 30 * 2

    def test_total_duration_of_empty_workout_is_zero(self):
        assert Workout(name="W").total_duration == 0

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(1200, "20min"), (0, "0min"), (90, "1:30"), (3600, "60min"), (59, "0:59")],
    )
    def test_duration_string_formatting(self, seconds, expected):
        workout = Workout(name="W", sections=[Section(duration=seconds, stroke_rate=20)])

        assert workout.total_duration_str == expected


class TestSummary:
    def test_work_section_summary_omits_prefix_and_extras(self):
        section = Section(duration=90, stroke_rate=22, tension=4)

        assert section.summary() == "1:30 @ 22spm T4 — No drills"

    def test_summary_includes_type_repeats_rest_and_drills(self):
        section = Section(
            duration=600,
            stroke_rate=18,
            tension=2,
            drills=[DrillEntry(DrillType.legs_only, 2)],
            repeats=4,
            section_type=SectionType.warmup,
            rest_after=30,
        )

        assert section.summary() == "[Warmup] 10:00 @ 18spm T2 x4 +30s rest — Legs Only"
