# CLAUDE.md

This file provides guidance to Claude Code when working on this project.

## Project Overview

PyRow is a visual rowing workout pacer built with pygame-ce and customtkinter.
It displays animated stroke guidance as an always-on-top overlay while rowing.

## Commands

- **Run the app**: `uv run python main.py`
- **Lint**: `uv run ruff check --fix .`
- **Format**: `uv run ruff format .`
- **Type check**: `uv run ty check`
- **All checks** (what pre-commit runs): `uv run pre-commit run --all-files`
- **Build docs**: `cd docs && uv run sphinx-build . _build`

## Architecture

- `main.py` — entry point, initializes pygame and launches SceneManager
- `models/workout.py` — data model: Workout, Section, SectionType, DrillEntry, DrillType, Level
- `workout_player.py` — state machine for timed workout playback
- `workout_store.py` — JSON persistence for workouts
- `scenes/menu.py` — customtkinter menu with filters and workout list
- `scenes/animation.py` — pygame animation scene (Rowing Figure V2 only)
- `animations/base.py` — DrillProfile, DRILL_PROFILES, get_position(), pause/transition math
- `animations/styles.py` — RowingFigureV2Animation, body_positions(), part coloring
- `ui/workout_editor.py` — customtkinter workout editor dialog
- `workouts.json` — workout library (60 workouts)

## Key Patterns

- **Scene system**: `SceneManager` runs the event loop, delegates to active `Scene`
- **Flat playback**: `Workout.flatten_sections()` expands repeats/rest for the player
- **Section types**: work, rest, warmup, cooldown — affect visual presentation and color
- **Drill cycling**: sections contain drill entries that rotate on each stroke
- **Smooth transitions**: `WorkoutPlayer` adjusts cycle time per section for whole-stroke boundaries; `get_position()` cosine-blends offsets on transition strokes
- **Catch position**: all drills map position 0.0 to catch (legs compressed, body forward, arms extended); drills with non-zero offsets use setup phases in `body_positions()`
- **Rest sections**: animate at 16 spm in light blue `(140, 200, 255)`; regular full stroke uses dark blue `(60, 120, 215)`
- **Pause drills**: `_DWELL = 0.44` (44% of stroke cycle) hold at the pause point; `_DRIVE = 0.34` for the drive phase
- **Level filtering**: menu filters by Level (beginner/intermediate/advanced) and duration range
- **Smooth scrolling**: `_SmoothScroller` lerp-eases mouse wheel on the workout list

## Code Style

- Python 3.14+, managed with `uv`
- Formatting and linting via `ruff` (config in pyproject.toml)
- Type checking via `ty`
- Pre-commit hooks enforce all checks on commit
- Line length: 120 characters
- Use `from __future__ import annotations` in all modules

## Working with Workouts

- `level` field on `Workout` — Level enum (beginner/intermediate/advanced), defaults to beginner, only serialized when non-default
- `description` field on `Workout` — optional, shown as tooltip on hover in menu
- `section_type` and `rest_after` are only serialized when non-default (backward compat)
- `rest_after` inserts rest between repeats (not after last) for multi-repeat sections
- `rest_after` inserts rest after the section for single-repeat sections
- Rest sections auto-generated with 16 spm and parent tension
