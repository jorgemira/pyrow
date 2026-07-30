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
- **All checks** (what pre-commit runs): `prek run --all-files`
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
- `workouts.json` — workout library (84 workouts)

## Key Patterns

- **Scene system**: `SceneManager` runs the event loop, delegates to active `Scene`
- **Flat playback**: `Workout.flatten_sections()` expands repeats/rest for the player
- **Section types**: work, rest, warmup, cooldown — affect visual presentation and color
- **Drill cycling**: sections contain drill entries that rotate on each stroke
- **Smooth transitions**: `WorkoutPlayer` adjusts cycle time per section for whole-stroke boundaries; `get_position()` cosine-blends offsets on transition strokes
- **Catch position**: all drills map position 0.0 to catch (legs compressed, body forward, arms extended); drills with non-zero offsets use setup phases in `body_positions()`
- **Rest sections**: animate at 16 spm in light blue `(140, 200, 255)`; regular full stroke uses dark blue `(60, 120, 215)`
- **Pause drills**: `_DWELL = 0.22` (22% of stroke cycle) hold at the pause point; `_DRIVE = 0.34` for the drive phase
- **Level filtering**: menu filters by Level (beginner/intermediate/advanced) and duration range
- **Smooth scrolling**: `_SmoothScroller` lerp-eases mouse wheel on the workout list
- **Resizable windows**: both menu and animation scenes scale proportionally; `_s()` scales reference pixel values, `_font()` scales text sizes, debounced via `after()` timer
- **Tooltip on hover**: `_Tooltip` class in menu shows `workout.description` after 1s delay
- **Stop confirmation**: clicking Stop/Escape pauses the workout and shows a modal confirmation dialog; Yes confirms, No dismisses but keeps paused
- **Progress bars below figure**: section and total progress bars are stacked below the animation area in `_bar_rect`, separate from the side panel
- **Seekable progress bars**: click-and-drag on either bar to scrub; `WorkoutPlayer.seek_section()` and `seek_total()` handle positioning; tooltip shows target time (total bar also shows section label)
- **Remaining sections list**: side panel shows a scrollable "Up next" list of all remaining sections (drill, rate, tension, duration); mouse wheel scrolls, scroll resets on section change
- **Ready prompt**: workout launches paused with a "Ready?" screen; user presses Space/Enter or clicks Start to begin; Escape returns to menu
- **Double-click to play**: double-clicking a workout in the menu list selects and launches it
- **Window placement**: animation window is pinned to the top-right of the primary monitor via `_top_right()`, which derives the monitor origin by centering the window and inverting the arithmetic (SDL doesn't report monitor origins)
- **Screen sleep allowed**: `pygame.display.set_allow_screensaver(True)` in `main.py` so the display can blank/sleep despite SDL's default

## Code Style

- Python 3.14+, managed with `uv`
- Formatting and linting via `ruff` (config in pyproject.toml)
- Type checking via `ty`
- Pre-commit hooks via `prek` (Rust-based, reads `.pre-commit-config.yaml`)
- Line length: 120 characters
- Use `from __future__ import annotations` in all modules

## Working with Workouts

- Workout names follow `Level - Name - Extra` format (e.g. "Intermediate - Pete Plan - Speed"); `workouts.json` is kept sorted by level, then duration
- `level` field on `Workout` — Level enum (beginner/intermediate/advanced), defaults to beginner, only serialized when non-default
- `description` field on `Workout` — optional, shown as tooltip on hover in menu
- `section_type` and `rest_after` are only serialized when non-default (backward compat)
- `rest_after` inserts rest between repeats (not after last) for multi-repeat sections
- `rest_after` inserts rest after the section for single-repeat sections
- Rest sections auto-generated with 16 spm and parent tension
