# PyRow

A visual rowing workout pacer. PyRow shows an animated rowing figure that paces your stroke, as an
always-on-top window you can keep beside the erg monitor.

![PyRow](pyrow.png)

## What it does

- Paces a full stroke or any of ten drills (arms only, legs only, pause at back, mid-slide, …), with
  the inactive body parts dimmed so it is obvious what should be moving
- Plays through a timed workout of warmup, work, rest and cooldown sections, cycling drills per
  stroke and beeping five seconds before each change
- Ships a library of 116 workouts filtered by level and duration, and an editor for your own
- Adjusts each section's stroke cycle so sections always begin and end at the catch

## Requirements

Python 3.14 and [uv](https://docs.astral.sh/uv/).

## Run it

```bash
uv run python main.py
```

Pick a workout, press Play (or double-click it), then Space or Enter to start.

### Controls

| Key | Action |
|---|---|
| `Space` | Pause / resume |
| `←` `→` | Previous / next section |
| `M` | Mute the beeps |
| `Esc` | Stop (asks to confirm) |

Both progress bars can be dragged to scrub. In the menu, `↑`/`↓` move through the list, `Enter`
plays the selection and `Esc` quits.

Workouts live in `workouts.json` next to the code, so the library travels with the checkout.

## Development

```bash
uv run pytest                 # tests
uv run ruff check --fix .     # lint
uv run ruff format .          # format
uv run ty check               # types
prek run --all-files          # everything the pre-commit hook runs
```

The animation tests run headless on SDL's dummy driver. The customtkinter tests need a display and
skip without one — use `xvfb-run uv run pytest` in a headless environment.

See `CLAUDE.md` for the architecture notes and `docs/` for the Sphinx documentation.
