from __future__ import annotations

import json
from pathlib import Path

from models.workout import Workout

WORKOUTS_FILE = Path(__file__).parent / "workouts.json"


def load_workouts() -> list[Workout]:
    """Load the workout library, failing with a message that names the offending entry."""
    if not WORKOUTS_FILE.exists():
        return []
    try:
        data = json.loads(WORKOUTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{WORKOUTS_FILE} is not valid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc

    workouts = []
    for i, raw in enumerate(data):
        try:
            workouts.append(Workout.from_dict(raw))
        except (KeyError, TypeError, ValueError) as exc:
            name = raw.get("name", "<unnamed>") if isinstance(raw, dict) else raw
            raise ValueError(f"{WORKOUTS_FILE}: entry {i} ({name!r}) is invalid: {exc}") from exc
    return workouts


def save_workouts(workouts: list[Workout]) -> None:
    """Write the library atomically, so an interrupted save cannot truncate it."""
    text = json.dumps([w.to_dict() for w in workouts], indent=2, ensure_ascii=False) + "\n"
    tmp = WORKOUTS_FILE.with_name(WORKOUTS_FILE.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(WORKOUTS_FILE)
