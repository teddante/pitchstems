# Quality Gate Roadmap

PitchStems currently runs Ruff, Vulture, mypy on a scoped set of hardened
modules, pytest with focused coverage gates, compileall, pip check, doctor,
GUI smoke, and package build in `scripts/check.ps1`.

## Current Typed Surface

The enforced mypy surface is listed in `pyproject.toml` under `[tool.mypy].files`.
It intentionally covers modules that are stable enough for strict typing without
large annotation churn.

## Known Gaps

- `src/pitchstems/app.py`: large PySide main-window class and nested callbacks.
- `src/pitchstems/gui_timeline.py`: large drawing/input surface.
- `src/pitchstems/chord_analysis.py`: large legacy analysis implementation.
- `src/pitchstems/scale_analysis.py`: large theory-analysis implementation.
- Native ML boundary modules still depend on third-party packages without stubs.

## Expansion Rule

When adding a module to strict mypy or coverage gates:

1. Add focused behavior tests first.
2. Add the smallest stable module to the gate.
3. Run `.\scripts\check.ps1`.
4. Do not lower coverage thresholds to make unrelated work pass.
