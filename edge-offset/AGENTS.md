# Repository Guidelines

## Project Structure & Module Organization

Core library code lives under `src/edge_offset/`.
Use:

- `geojson.py` for GeoJSON feature collection I/O
- `linework.py` for rebuilding polygons from edge linework
- `polygon_ops.py` for polygon geometry transforms

Tests live in `tests/`. Keep new unit tests beside the module they cover, for example
`tests/test_polygon_ops.py`. Sample spatial fixtures live in `tests/data/` and should stay small,
deterministic, and easy to inspect.

## Build, Test, and Development Commands

- `uv sync`: create or update the local environment from `pyproject.toml` and `uv.lock`
- `uv run pytest`: run the full test suite
- `uv run pytest tests/test_polygon_ops.py`: run one test file during iteration
- `uv run ruff check .`: run lint checks

This repository is a library, not an application, so there is no local server or CLI entry point.

## Coding Style & Naming Conventions

Target Python 3.12 and keep code compatible with the `uv` environment defined in `pyproject.toml`.
Use 4-space indentation, `pathlib.Path`, and type hints throughout. Favor small, explicit functions
with direct validation over exception-driven control flow.

Naming:

- modules: lowercase with underscores
- functions and variables: `snake_case`
- classes and dataclasses: `PascalCase`
- tests: `test_<behavior>.py` and `test_<expected_outcome>()`

Use `ruff` for linting. Keep public APIs minimal and avoid re-export-heavy package layouts.

## Testing Guidelines

Write pytest tests for all geometry changes. Cover both simple synthetic polygons and fixture-based
cases from `tests/data/` when changing spatial reconstruction behavior. Prefer exact geometric
assertions where stable, and validity checks such as `polygon.is_valid` for complex fixtures.

## Commit & Pull Request Guidelines

Recent commits use short, lowercase, imperative messages such as `fix typo` and `b6c5c9d edges`.
Follow that pattern and keep each commit focused on one change.

Pull requests should include:

- a short description of the geometry or API change
- notes on affected fixtures or assumptions
- the commands you ran, usually `uv run pytest` and `uv run ruff check .`
