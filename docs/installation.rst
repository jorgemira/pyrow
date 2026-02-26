Installation
============

Requirements
------------

- Python 3.14 or later
- `uv <https://docs.astral.sh/uv/>`_ package manager

Setup
-----

Clone the repository and install dependencies::

    git clone <repository-url>
    cd pyrow
    uv sync

This installs both runtime dependencies (``pygame-ce``, ``customtkinter``) and
development tools (``ruff``, ``ty``, ``pre-commit``, ``sphinx``).

Development Setup
-----------------

Install pre-commit hooks to enforce code quality on every commit::

    uv run pre-commit install

The hooks run automatically on ``git commit`` and will:

- Fix trailing whitespace and missing end-of-file newlines
- Sort and lint imports with ``ruff``
- Format code with ``ruff format``
- Type-check with ``ty``

Running Tools Manually
----------------------

Lint and auto-fix::

    uv run ruff check --fix .

Format::

    uv run ruff format .

Type check::

    uv run ty check
