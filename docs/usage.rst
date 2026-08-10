Usage
=====

Starting PyRow
--------------

Run from the project root::

    uv run python main.py

Or via the installed script entry point::

    uv run pyrow

Menu Screen
-----------

The application opens with a customtkinter menu that lists all available
workouts loaded from ``workouts.json``. From the menu you can:

- **Select a workout** from the scrollable list — hover for ~1 second to see a
  description tooltip, or use the arrow keys
- **Filter** by level and by duration range
- **Play** the selected workout to launch the animation scene — click Play,
  double-click the row, or press Enter
- **Edit** or **create** workouts using the built-in editor
- **Delete** workouts you no longer need
- **Quit** with the Exit button or Escape

Workout Editor
--------------

The editor dialog lets you build workouts section by section:

- Set **duration**, **stroke rate**, **tension**, and **repeats** per section
- Assign a **section type** (Work, Rest, Warmup, Cooldown) to control visual
  presentation during playback
- Set **rest after** (seconds) to auto-insert rest periods between repeats
- Add **drill entries** to each section — drills cycle through on each stroke

Animation Scene
---------------

During playback the animation window stays always-on-top so you can read it
from your rowing machine. The left panel shows:

- Current drill name (or "REST" in grey during rest sections)
- Stroke rate, tension, and section label
- Section and total progress bars
- A "HOLD" stop sign during pause points in the stroke cycle

Controls:

========== =============================================
Key        Action
========== =============================================
Space      Play / Pause (starts the workout when ready)
Escape     Stop, after a confirmation prompt
Left/Right Previous / Next section
M          Mute / Unmute transition sounds
========== =============================================

On-screen buttons mirror the keyboard controls. Both progress bars can be
clicked or dragged to scrub; the tooltip shows the target time, and the total
bar also names the section you are scrubbing to.
