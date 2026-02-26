Architecture
============

PyRow is organized into five packages around a scene-manager pattern.

Module Overview
---------------

::

    pyrow/
    ├── main.py              # Entry point — initializes pygame, launches SceneManager
    ├── workout_player.py    # State machine for timed workout playback
    ├── workout_store.py     # JSON persistence for workouts
    ├── workouts.json        # Default workout library
    ├── models/
    │   └── workout.py       # Data model: Workout, Section, SectionType, DrillEntry
    ├── scenes/
    │   ├── base.py          # Abstract Scene class
    │   ├── manager.py       # SceneManager — runs the pygame event loop
    │   ├── menu.py          # Workout selection menu (customtkinter)
    │   └── animation.py     # Playback scene with visual overlay
    ├── animations/
    │   ├── base.py          # DrillProfile, BaseAnimation, position math
    │   └── styles.py        # Concrete animation renderers
    └── ui/
        └── workout_editor.py  # Section editor dialog (customtkinter)

Data Model
----------

``Workout``
    A named collection of ``Section`` objects. Provides ``flatten_sections()``
    which expands repeats and inserts rest periods for playback.

``Section``
    A timed interval with stroke rate, tension, drill pattern, section type,
    repeat count, and optional rest-after duration.

``SectionType``
    Enum: ``work``, ``rest``, ``warmup``, ``cooldown``. Controls visual
    presentation and warning text during playback.

``DrillEntry``
    A drill type paired with a stroke count. Sections contain a list of drill
    entries that cycle on each stroke.

Scene System
------------

``SceneManager`` owns the pygame clock and event loop. It delegates to the
active ``Scene`` which implements ``enter()``, ``exit()``, ``handle_event()``,
``update()``, and ``draw()``.

Two scenes exist:

- ``MenuScene`` — opens a customtkinter window for workout selection and
  editing. Blocks in ``enter()`` via ``mainloop()``.
- ``AnimationScene`` — creates an always-on-top pygame window and runs the
  ``WorkoutPlayer`` state machine at 60 fps.

WorkoutPlayer
-------------

A state machine (``stopped → playing → paused → finished``) that:

1. Flattens the workout's sections via ``flatten_sections()``
2. Tracks elapsed time per section and overall
3. Fires a 5-second warning before each section transition
4. Provides the current stroke phase (0.0–1.0) for animation
5. Cycles through drill entries based on stroke count

Animation System
----------------

``DrillProfile`` defines per-drill stroke geometry: range of motion, pauses,
and colors. ``get_position()`` converts the stroke phase into a normalized
body position. Concrete ``BaseAnimation`` subclasses render the position onto
the pygame surface — styles include stick figures, progress bars, and particle
effects.
