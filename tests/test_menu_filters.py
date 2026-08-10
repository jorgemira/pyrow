"""Tests for the menu's duration filter predicate."""

from __future__ import annotations

import pytest

from models.workout import Section, Workout
from scenes.menu import _DURATION_FILTERS, _duration_matches


def workout_of(minutes: float) -> Workout:
    return Workout(name="W", sections=[Section(duration=int(minutes * 60), stroke_rate=20)])


@pytest.mark.parametrize("filt", _DURATION_FILTERS)
def test_all_filter_labels_are_understood(filt):
    """A label in the dropdown that the predicate does not handle would silently match everything."""
    matches = {m: _duration_matches(workout_of(m), filt) for m in (5, 25, 40, 60)}

    assert matches != {} and (filt == "All") == all(matches.values())


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (19.9, "< 20min"),
        (20, "20-30min"),
        (25, "20-30min"),
        (30, "20-30min"),
        (30.5, "30-45min"),
        (45, "30-45min"),
        (46, "> 45min"),
    ],
)
def test_each_duration_falls_in_exactly_one_bucket(minutes, expected):
    buckets = [f for f in _DURATION_FILTERS if f != "All" and _duration_matches(workout_of(minutes), f)]

    assert buckets == [expected]


def test_all_matches_every_duration():
    assert all(_duration_matches(workout_of(m), "All") for m in (0, 1, 100))


def test_boundaries_are_inclusive_as_labelled():
    assert _duration_matches(workout_of(20), "20-30min")
    assert not _duration_matches(workout_of(20), "< 20min")
    assert _duration_matches(workout_of(30), "20-30min")
    assert not _duration_matches(workout_of(30), "30-45min")
