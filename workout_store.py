from __future__ import annotations

import json
from pathlib import Path

from models.workout import Workout

WORKOUTS_FILE = Path(__file__).parent / "workouts.json"


def load_workouts() -> list[Workout]:
    if not WORKOUTS_FILE.exists():
        return []
    data = json.loads(WORKOUTS_FILE.read_text(encoding="utf-8"))
    return [Workout.from_dict(w) for w in data]


def save_workouts(workouts: list[Workout]) -> None:
    data = [w.to_dict() for w in workouts]
    WORKOUTS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
