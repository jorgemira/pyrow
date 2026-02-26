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
- **All checks** (what prek runs): `prek run --all-files`
- **Build docs**: `cd docs && uv run sphinx-build . _build`

## Architecture

- `main.py` — entry point, initializes pygame and launches SceneManager
- `models/workout.py` — data model: Workout, Section, SectionType, DrillEntry, DrillType
- `workout_player.py` — state machine for timed workout playback
- `workout_store.py` — JSON persistence for workouts
- `scenes/` — scene system (base, manager, menu, animation)
- `animations/` — drill profiles and visual renderers
- `ui/workout_editor.py` — customtkinter section editor dialog
- `workouts.json` — default workout library

## Key Patterns

- **Scene system**: `SceneManager` runs the event loop, delegates to active `Scene`
- **Flat playback**: `Workout.flatten_sections()` expands repeats/rest for the player
- **Section types**: work, rest, warmup, cooldown — affect visual presentation only
- **Drill cycling**: sections contain drill entries that rotate on each stroke

## Code Style

- Python 3.14+, managed with `uv`
- Formatting and linting via `ruff` (config in pyproject.toml)
- Type checking via `ty`
- prek hooks enforce all checks on commit
- Line length: 120 characters
- Use `from __future__ import annotations` in all modules

## Working with Workouts

- `description` field on `Workout` — optional, shown as tooltip on hover in menu
- `section_type` and `rest_after` are only serialized when non-default (backward compat)
- `rest_after` inserts rest between repeats (not after last) for multi-repeat sections
- `rest_after` inserts rest after the section for single-repeat sections
- Rest sections auto-generated with 16 spm and parent tension
