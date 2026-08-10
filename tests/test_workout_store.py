"""Tests for JSON persistence of the workout library."""

from __future__ import annotations

import json

import pytest

import workout_store
from models.workout import DrillEntry, DrillType, Level, Section, Workout
from workout_store import load_workouts, save_workouts


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "workouts.json"
    monkeypatch.setattr(workout_store, "WORKOUTS_FILE", path)
    return path


def test_missing_file_yields_an_empty_library(store):
    assert not store.exists()
    assert load_workouts() == []


def test_save_then_load_round_trips(store):
    workouts = [
        Workout(
            name="Intermediate - Test - Speed",
            description="desc",
            level=Level.intermediate,
            sections=[Section(duration=300, stroke_rate=24, drills=[DrillEntry(DrillType.legs_only, 2)])],
        ),
        Workout(name="Beginner - Simple", sections=[Section(duration=600, stroke_rate=20)]),
    ]

    save_workouts(workouts)

    assert load_workouts() == workouts


def test_saved_file_is_human_editable(store):
    save_workouts([Workout(name="Ünïcode", sections=[Section(duration=60, stroke_rate=20)])])

    text = store.read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert "  " in text, "indented for hand editing"
    assert "Ünïcode" in text, "unicode is not escaped"


def test_empty_library_saves_and_loads(store):
    save_workouts([])

    assert json.loads(store.read_text(encoding="utf-8")) == []
    assert load_workouts() == []


def test_malformed_json_reports_where_it_broke(store):
    store.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="is not valid JSON at line 1 column 2"):
        load_workouts()


def test_invalid_entry_names_the_workout_and_the_cause(store):
    store.write_text(
        json.dumps([{"name": "Good", "sections": []}, {"name": "Bad", "sections": [{"stroke_rate": 20}]}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"entry 1 \('Bad'\) is invalid"):
        load_workouts()


def test_unnamed_invalid_entry_still_reports_its_position(store):
    store.write_text(json.dumps([{"sections": []}]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"entry 0 \('<unnamed>'\) is invalid"):
        load_workouts()


def test_save_is_atomic_and_leaves_no_temp_file(store):
    save_workouts([Workout(name="A", sections=[Section(duration=60, stroke_rate=20)])])

    assert not store.with_name(store.name + ".tmp").exists()
    assert [w.name for w in load_workouts()] == ["A"]


def test_a_failed_save_leaves_the_previous_library_intact(store, monkeypatch):
    save_workouts([Workout(name="Original", sections=[Section(duration=60, stroke_rate=20)])])
    original = store.read_text(encoding="utf-8")

    class Unserialisable:
        def to_dict(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        save_workouts([Unserialisable()])  # type: ignore[list-item]

    assert store.read_text(encoding="utf-8") == original, "the old library must survive a failed write"


def test_the_shipped_library_loads_and_is_well_formed():
    """Guards the checked-in workouts.json against edits that would break playback."""
    workouts = load_workouts()

    assert len(workouts) > 0
    for workout in workouts:
        assert workout.name.strip(), "every workout needs a name"
        assert workout.flatten_sections(), f"{workout.name} has no playable sections"
        for section in workout.sections:
            assert section.duration >= 1, f"{workout.name}: non-positive duration"
            assert section.stroke_rate >= 1, f"{workout.name}: non-positive stroke rate"
            assert section.repeats >= 1, f"{workout.name}: non-positive repeats"
            assert 1 <= section.tension <= 8, f"{workout.name}: tension out of range"
