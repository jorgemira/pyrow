Workout Format
==============

Workouts are stored in ``workouts.json`` as a JSON array. Each workout object
contains a name and a list of sections.

JSON Schema
-----------

.. code-block:: json

    {
      "name": "Interval 6x2min (23min)",
      "description": "Classic 6x2-minute interval workout with 60-second rest.",
      "sections": [
        {
          "duration": 180,
          "stroke_rate": 18,
          "tension": 3,
          "drills": [],
          "repeats": 1,
          "section_type": "warmup"
        },
        {
          "duration": 120,
          "stroke_rate": 24,
          "tension": 4,
          "drills": [],
          "repeats": 6,
          "rest_after": 60
        },
        {
          "duration": 180,
          "stroke_rate": 16,
          "tension": 3,
          "drills": [],
          "repeats": 1,
          "section_type": "cooldown"
        }
      ]
    }

Workout Fields
--------------

==================  ========  =======  ================================================
Field               Type      Default  Description
==================  ========  =======  ================================================
``name``            string    —        Display name of the workout
``description``     string    ""       Optional short description (shown as hover tooltip)
``sections``        array     []       List of section objects (see below)
==================  ========  =======  ================================================

Section Fields
--------------

==================  ========  =======  ================================================
Field               Type      Default  Description
==================  ========  =======  ================================================
``duration``        int       —        Length in seconds
``stroke_rate``     int       —        Target strokes per minute
``tension``         int       3        Machine resistance (1–8)
``drills``          array     []       List of drill entries (see below)
``repeats``         int       1        Number of times to repeat this section
``section_type``    string    "work"   One of: ``work``, ``rest``, ``warmup``, ``cooldown``
``rest_after``      int       0        Seconds of rest inserted between repeats
==================  ========  =======  ================================================

``section_type`` and ``rest_after`` are only written to JSON when they differ
from their defaults, preserving backward compatibility with older workout files.

Section Types
-------------

``work``
    Standard rowing section. Displayed with drill-colored text and progress bar.

``rest``
    Recovery period. Displayed as "REST" in grey with a grey progress bar.
    Auto-generated rest sections use 16 spm and inherit the parent section's
    tension.

``warmup``
    Pre-workout warm-up. Prefixed with "Warmup:" in the drill display.

``cooldown``
    Post-workout cool-down. Prefixed with "Cooldown:" in the drill display.

Repeats and Rest
----------------

The ``repeats`` field duplicates a section for playback. When combined with
``rest_after``, rest periods are automatically inserted:

- **Multi-repeat** (``repeats > 1``): rest is inserted *between* repeats, not
  after the last one. Example: ``repeats=6, rest_after=60`` produces 6 work
  sections and 5 rest sections (11 total).

- **Single section** (``repeats = 1``): rest is inserted *after* the section.
  Useful for pyramid workouts where each step has a different duration.

The ``Workout.flatten_sections()`` method expands repeats and inserts rest
sections to produce a flat list for the player.

Drill Entries
-------------

Each drill entry has a ``type`` and ``count``:

.. code-block:: json

    {"type": "arms_only", "count": 4}

Available drill types:

- ``none`` — full stroke (no restriction)
- ``arms_only``
- ``arms_and_hips``
- ``hips_and_legs``
- ``legs_only``
- ``mid_slide``
- ``pause_at_back``
- ``pause_at_front``
- ``pause_arms_away``
- ``pause_body_over``

Drills cycle through the list on each stroke. A section with
``[{"type": "arms_only", "count": 4}, {"type": "none", "count": 2}]``
alternates 4 arms-only strokes with 2 full strokes, repeating.
