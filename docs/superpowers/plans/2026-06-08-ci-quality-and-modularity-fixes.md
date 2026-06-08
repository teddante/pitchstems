# CI Quality And Modularity Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the June 8, 2026 audit findings by aligning CI with local validation, strengthening ML import checks, expanding scoped quality gates, and continuing module-boundary extractions without breaking the current PySide app.

**Architecture:** First make CI and local validation use the same command path, because that protects every later slice. Then add an import-level ML smoke that avoids heavy inference. Finally, reduce maintainability pressure with compatibility-preserving pure-module extractions from chord-gap, timeline, and chord naming code.

**Tech Stack:** Python 3.10, PowerShell, GitHub Actions, pytest, pytest-cov, mypy, Ruff, PySide6.

---

## File Structure

- Modify: `scripts/check.ps1`
  - Discover `python` and `pitchstems` outside `.venv` so GitHub Actions can run the same script as local development.
- Modify: `.github/workflows/ci.yml`
  - Replace duplicated direct CI commands with `.\scripts\check.ps1 -GuiSmoke -Build`.
- Create: `scripts/ml_import_smoke.py`
  - Import ML runtime packages and print installed versions without loading models or running inference.
- Modify: `.github/workflows/ml-dependencies.yml`
  - Run the ML import smoke after installing `.[cpu]`.
- Modify: `pyproject.toml`
  - Expand the scoped mypy target list to the next pure modules.
- Modify: `scripts/check.ps1`
  - Expand coverage gate modules alongside the expanded mypy scope.
- Create: `src/pitchstems/theory_helpers.py`
  - Hold public pure theory helper functions shared by scale and chord-gap analysis.
- Modify: `src/pitchstems/scale_analysis.py`
  - Import helpers from `theory_helpers` and keep private aliases for compatibility.
- Modify: `src/pitchstems/chord_gap_analysis.py`
  - Import shared models from `editor_models` and public helpers from `theory_helpers`.
- Create: `src/pitchstems/timeline_chord_geometry.py`
  - Extract pure chord-label and chord-snap helpers from `TimelineView`.
- Modify: `src/pitchstems/gui_timeline.py`
  - Delegate compact chord labels and chord drag snap bounds to `timeline_chord_geometry`.
- Create: `src/pitchstems/chord_naming.py`
  - Extract chord label display and chord-tone naming helpers from `chord_analysis`.
- Modify: `src/pitchstems/chord_analysis.py`
  - Re-export extracted naming helpers for import compatibility.
- Modify tests:
  - `tests/test_theory.py`
  - `tests/test_gui_timeline.py`
  - `tests/test_chord_analysis.py`

---

### Task 1: Make `check.ps1` Usable As The CI Entry Point

**Files:**
- Modify: `scripts/check.ps1`

- [ ] **Step 1: Add command discovery helpers**

Replace the current `$python` and `$pitchstems` setup near the top of `scripts/check.ps1` with:

```powershell
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$venvPitchstems = Join-Path $PSScriptRoot "..\.venv\Scripts\pitchstems.exe"

if (Test-Path $venvPython) {
    $python = $venvPython
    $pythonArgs = @()
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        $python = $pythonCommand.Source
        $pythonArgs = @()
    } else {
        $python = "py"
        $pythonArgs = @("-3.10")
    }
}

if (Test-Path $venvPitchstems) {
    $pitchstems = $venvPitchstems
} else {
    $pitchstemsCommand = Get-Command pitchstems -ErrorAction SilentlyContinue
    if ($null -ne $pitchstemsCommand) {
        $pitchstems = $pitchstemsCommand.Source
    } else {
        $pitchstems = $null
    }
}
```

- [ ] **Step 2: Update doctor launcher condition**

Replace:

```powershell
if (Test-Path $pitchstems) {
```

with:

```powershell
if ($null -ne $pitchstems -and (Test-Path $pitchstems)) {
```

- [ ] **Step 3: Run the script locally**

Run:

```powershell
.\scripts\check.ps1
```

Expected: whitespace, Ruff, mypy, tests with coverage, compile, pip check, and doctor pass.

- [ ] **Step 4: Commit the script portability fix**

Run:

```powershell
git add scripts/check.ps1
git commit -m "build: make check script portable for CI"
```

---

### Task 2: Align GitHub CI With Local Validation

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Replace duplicated CI validation steps**

In `.github/workflows/ci.yml`, keep checkout, Python setup, and package installation. Replace the separate whitespace, lint, test, compile, pip check, GUI smoke, and build steps with:

```yaml
      - name: Run project checks
        shell: pwsh
        env:
          QT_QPA_PLATFORM: offscreen
        run: .\scripts\check.ps1 -GuiSmoke -Build
```

The resulting job should still install `.[dev,gui]` before this step:

```yaml
      - name: Install package and dev tools
        run: |
          python -m pip install -U pip
          python -m pip install -e ".[dev,gui]"
```

- [ ] **Step 2: Verify the workflow references the project smoke path**

Run:

```powershell
rg -n "check.ps1 -GuiSmoke -Build|QT_QPA_PLATFORM|PITCHSTEMS_GUI_SMOKE|python -m pytest|python -m ruff" .github/workflows/ci.yml scripts/check.ps1
```

Expected:
- `.github/workflows/ci.yml` contains `.\scripts\check.ps1 -GuiSmoke -Build`.
- `scripts/check.ps1` contains `PITCHSTEMS_GUI_SMOKE = "project"`.
- `.github/workflows/ci.yml` no longer contains direct `python -m pytest` or direct `python -m ruff` validation steps.

- [ ] **Step 3: Run local full verification**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
```

Expected: PASS.

- [ ] **Step 4: Commit the CI parity fix**

Run:

```powershell
git add .github/workflows/ci.yml
git commit -m "ci: run canonical project checks"
```

---

### Task 3: Add ML Import-Level Validation

**Files:**
- Create: `scripts/ml_import_smoke.py`
- Modify: `.github/workflows/ml-dependencies.yml`

- [ ] **Step 1: Create the ML import smoke script**

Create `scripts/ml_import_smoke.py`:

```python
from __future__ import annotations

import importlib
import importlib.metadata


RUNTIME_MODULES = {
    "basic-pitch": "basic_pitch",
    "bs-roformer-infer": "bs_roformer",
    "torch": "torch",
}


def main() -> int:
    for distribution, module_name in RUNTIME_MODULES.items():
        module = importlib.import_module(module_name)
        version = importlib.metadata.version(distribution)
        print(f"OK {distribution} {version}: imported {module.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the smoke locally**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\ml_import_smoke.py
```

Expected output contains:

```text
OK basic-pitch
OK bs-roformer-infer
OK torch
```

- [ ] **Step 3: Wire it into the ML dependency workflow**

In `.github/workflows/ml-dependencies.yml`, after `python -m pip check`, add:

```yaml
      - name: Import ML packages
        run: python scripts/ml_import_smoke.py
```

- [ ] **Step 4: Verify local checks**

Run:

```powershell
git diff --check
.\scripts\check.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit the ML import smoke**

Run:

```powershell
git add scripts/ml_import_smoke.py .github/workflows/ml-dependencies.yml
git commit -m "ci: import ML runtime packages"
```

---

### Task 4: Expand Scoped Type And Coverage Gates

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/check.ps1`

- [ ] **Step 1: Expand mypy target files**

In `pyproject.toml`, update `[tool.mypy].files` to:

```toml
files = [
  "src/pitchstems/editor_models.py",
  "src/pitchstems/gui_jobs.py",
  "src/pitchstems/project_store.py",
  "src/pitchstems/recent_projects.py",
  "src/pitchstems/time_format.py",
]
```

- [ ] **Step 2: Expand coverage modules**

In `scripts/check.ps1`, replace the pytest coverage arguments with:

```powershell
        --cov=pitchstems.editor_models `
        --cov=pitchstems.gui_jobs `
        --cov=pitchstems.project_store `
        --cov=pitchstems.recent_projects `
        --cov=pitchstems.time_format `
        --cov-report=term-missing `
        --cov-fail-under=90
```

- [ ] **Step 3: Run mypy and coverage**

Run:

```powershell
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov=pitchstems.editor_models --cov=pitchstems.gui_jobs --cov=pitchstems.project_store --cov=pitchstems.recent_projects --cov=pitchstems.time_format --cov-report=term-missing --cov-fail-under=90
```

Expected: mypy succeeds and coverage remains at or above 90%.

- [ ] **Step 4: Run full local check**

Run:

```powershell
.\scripts\check.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit the gate expansion**

Run:

```powershell
git add pyproject.toml scripts/check.ps1
git commit -m "test: expand scoped quality gates"
```

---

### Task 5: Remove Chord-Gap Private Helper Coupling

**Files:**
- Create: `src/pitchstems/theory_helpers.py`
- Modify: `src/pitchstems/scale_analysis.py`
- Modify: `src/pitchstems/chord_gap_analysis.py`
- Modify: `tests/test_theory.py`

- [ ] **Step 1: Add tests for the public helper module**

Append to `tests/test_theory.py`:

```python
def test_theory_helpers_expose_gap_support_functions() -> None:
    from pitchstems.editor_models import ChordRegion, NoteEvent
    from pitchstems.theory_helpers import (
        candidate_common_tones,
        next_chord,
        previous_chord,
        region_energy,
        report_time,
    )

    chords = [
        ChordRegion(0.0, 1.0, "C", 0.9),
        ChordRegion(2.0, 3.0, "G", 0.9),
    ]
    notes = [NoteEvent("piano", 1.25, 1.75, 60, 100)]

    assert previous_chord(chords, 1.5) == chords[0]
    assert next_chord(chords, 1.5) == chords[1]
    assert region_energy(notes, 1.0, 2.0) > 0.0
    assert candidate_common_tones({0, 4, 7}, {7, 11, 2}) > 0.0
    assert report_time(65.0) == "1:05"
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_theory.py::test_theory_helpers_expose_gap_support_functions -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pitchstems.theory_helpers'`.

- [ ] **Step 3: Create `theory_helpers.py`**

Create `src/pitchstems/theory_helpers.py` with:

```python
from __future__ import annotations

from pitchstems.editor_models import ChordRegion, NoteEvent
```

Then move the existing helper bodies from `scale_analysis.py` into that file and rename each function as follows:

| Existing function in `scale_analysis.py` | New public function in `theory_helpers.py` |
| --- | --- |
| `_diatonic_chord_labels` | `diatonic_chord_labels` |
| `_candidate_theory_fit` | `candidate_theory_fit` |
| `_candidate_pitch_class_movement` | `candidate_pitch_class_movement` |
| `_candidate_common_tones` | `candidate_common_tones` |
| `_previous_chord` | `previous_chord` |
| `_next_chord` | `next_chord` |
| `_region_energy` | `region_energy` |
| `fit_clamp` | `fit_clamp` |
| `_report_time` | `report_time` |

Use the existing implementations from `scale_analysis.py` exactly, changing only the function names listed in the table and the model import to `pitchstems.editor_models`.

- [ ] **Step 4: Preserve scale-analysis compatibility aliases**

In `src/pitchstems/scale_analysis.py`, import the public helpers with private aliases:

```python
from pitchstems.theory_helpers import (
    candidate_common_tones as _candidate_common_tones,
    candidate_pitch_class_movement as _candidate_pitch_class_movement,
    candidate_theory_fit as _candidate_theory_fit,
    diatonic_chord_labels as _diatonic_chord_labels,
    fit_clamp,
    next_chord as _next_chord,
    previous_chord as _previous_chord,
    region_energy as _region_energy,
    report_time as _report_time,
)
```

Remove the old helper function definitions from `scale_analysis.py` after the import is in place.

- [ ] **Step 5: Update chord-gap imports to public modules**

In `src/pitchstems/chord_gap_analysis.py`, replace:

```python
from pitchstems.editor_project import ChordRegion, NoteEvent
from pitchstems.scale_analysis import (
    TheoryAnalysis,
    _candidate_common_tones,
    _candidate_pitch_class_movement,
    _candidate_theory_fit,
    _diatonic_chord_labels,
    _next_chord,
    _previous_chord,
    _region_energy,
    _report_time,
    analyze_theory_region,
    fit_clamp,
)
```

with:

```python
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.scale_analysis import TheoryAnalysis, analyze_theory_region
from pitchstems.theory_helpers import (
    candidate_common_tones,
    candidate_pitch_class_movement,
    candidate_theory_fit,
    diatonic_chord_labels,
    fit_clamp,
    next_chord,
    previous_chord,
    region_energy,
    report_time,
)
```

Then replace helper calls:

```python
_previous_chord -> previous_chord
_next_chord -> next_chord
_diatonic_chord_labels -> diatonic_chord_labels
_candidate_theory_fit -> candidate_theory_fit
_candidate_pitch_class_movement -> candidate_pitch_class_movement
_candidate_common_tones -> candidate_common_tones
_region_energy -> region_energy
_report_time -> report_time
```

- [ ] **Step 6: Run theory tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_theory.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit helper extraction**

Run:

```powershell
git add src/pitchstems/theory_helpers.py src/pitchstems/scale_analysis.py src/pitchstems/chord_gap_analysis.py tests/test_theory.py
git commit -m "refactor: share public theory helpers"
```

---

### Task 6: Extract Timeline Chord Geometry Helpers

**Files:**
- Create: `src/pitchstems/timeline_chord_geometry.py`
- Modify: `src/pitchstems/gui_timeline.py`
- Modify: `tests/test_gui_timeline.py`

- [ ] **Step 1: Add pure helper tests**

Append to `tests/test_gui_timeline.py`:

```python
def test_timeline_chord_geometry_snaps_inside_neighbour_bounds() -> None:
    from pitchstems.editor_models import ChordRegion
    from pitchstems.timeline_chord_geometry import snap_chord_seconds

    original = ChordRegion(start=2.0, end=4.0, label="Cmaj7", confidence=0.9)
    previous = ChordRegion(start=0.0, end=1.5, label="F", confidence=0.8)
    next_chord = ChordRegion(start=5.0, end=6.0, label="G", confidence=0.8)

    start, end = snap_chord_seconds(
        original=original,
        proposed_start=1.0,
        proposed_end=5.5,
        previous_chord=previous,
        next_chord=next_chord,
        duration=8.0,
        minimum_duration=0.05,
    )

    assert start == 1.5
    assert end == 5.0
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_timeline.py::test_timeline_chord_geometry_snaps_inside_neighbour_bounds -q
```

Expected: FAIL because `pitchstems.timeline_chord_geometry` does not exist.

- [ ] **Step 3: Create the helper module**

Create `src/pitchstems/timeline_chord_geometry.py`:

```python
from __future__ import annotations

import re

from pitchstems.editor_models import ChordRegion


def compact_chord_label(label: str) -> str:
    match = re.match(r"\s*([A-G](?:#|b)?)", label)
    return match.group(1) if match else label.strip()[:2]


def snap_chord_seconds(
    *,
    original: ChordRegion,
    proposed_start: float,
    proposed_end: float,
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
    duration: float,
    minimum_duration: float,
) -> tuple[float, float]:
    left_limit = previous_chord.end if previous_chord else 0.0
    right_limit = next_chord.start if next_chord else duration
    start = max(left_limit, min(proposed_start, right_limit - minimum_duration))
    end = min(right_limit, max(proposed_end, start + minimum_duration))
    if original.start == original.end:
        return start, end
    return start, end
```

- [ ] **Step 4: Delegate compact labels from `gui_timeline.py`**

In `src/pitchstems/gui_timeline.py`, remove `import re`, remove the local `compact_chord_label()` function, and add:

```python
from pitchstems.timeline_chord_geometry import compact_chord_label, snap_chord_seconds
```

- [ ] **Step 5: Delegate snap bounds from `_snap_seconds()`**

Replace the body of `TimelineView._snap_seconds()` with:

```python
        if not self.project:
            return seconds, seconds
        previous_chord, next_chord = self._neighbour_chords(ignored_chord)
        return snap_chord_seconds(
            original=ignored_chord,
            proposed_start=seconds,
            proposed_end=seconds + ignored_chord.duration,
            previous_chord=previous_chord,
            next_chord=next_chord,
            duration=self.project.duration,
            minimum_duration=0.05,
        )
```

- [ ] **Step 6: Run timeline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_timeline.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit timeline extraction**

Run:

```powershell
git add src/pitchstems/timeline_chord_geometry.py src/pitchstems/gui_timeline.py tests/test_gui_timeline.py
git commit -m "refactor: extract timeline chord geometry"
```

---

### Task 7: Extract Chord Naming Helpers

**Files:**
- Create: `src/pitchstems/chord_naming.py`
- Modify: `src/pitchstems/chord_analysis.py`
- Modify: `tests/test_chord_analysis.py`

- [ ] **Step 1: Add import compatibility tests**

Append to `tests/test_chord_analysis.py`:

```python
def test_chord_naming_module_exposes_public_helpers() -> None:
    from pitchstems.chord_naming import (
        chord_pitch_classes_for_label,
        chord_tones_for_label,
        display_chord_label,
    )

    assert display_chord_label("Cmaj7") == "Cmaj7"
    assert chord_pitch_classes_for_label("Cmaj7") == [0, 4, 7, 11]
    assert chord_tones_for_label("Cmaj7") == ["C", "E", "G", "B"]
```

- [ ] **Step 2: Verify the test fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chord_analysis.py::test_chord_naming_module_exposes_public_helpers -q
```

Expected: FAIL because `pitchstems.chord_naming` does not exist.

- [ ] **Step 3: Create `chord_naming.py`**

Create `src/pitchstems/chord_naming.py` and move these existing helper definitions from `chord_analysis.py` into it without changing behavior:

```python
display_chord_label
chord_tones_for_label
alternate_chord_names_for_label
exact_chord_names_for_pitch_classes
chord_pitch_classes_for_label
chord_bass_name_for_label
```

Also move the constants those helpers require, including pitch-class name tables, chord quality interval tables, and spelling helpers that are only used by those naming functions.

- [ ] **Step 4: Preserve `chord_analysis` compatibility**

In `src/pitchstems/chord_analysis.py`, import and re-export the moved helpers:

```python
from pitchstems.chord_naming import (
    alternate_chord_names_for_label,
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_tones_for_label,
    display_chord_label,
    exact_chord_names_for_pitch_classes,
)
```

Remove the old duplicate helper definitions from `chord_analysis.py` after all tests pass.

- [ ] **Step 5: Run chord tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chord_analysis.py tests/test_theory.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit chord naming extraction**

Run:

```powershell
git add src/pitchstems/chord_naming.py src/pitchstems/chord_analysis.py tests/test_chord_analysis.py
git commit -m "refactor: extract chord naming helpers"
```

---

### Task 8: Final Verification And PR Update

**Files:**
- No direct source changes beyond previous tasks.

- [ ] **Step 1: Run full local verification**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
git diff --check main...HEAD
```

Expected: PASS.

- [ ] **Step 2: Push the branch**

Run:

```powershell
git status --short --branch
git push
```

Expected: the working tree is clean before push, then `fix/audit-hardening` updates on GitHub.

- [ ] **Step 3: Verify PR checks**

Run:

```powershell
gh pr checks 6 --watch --interval 10
gh pr view 6 --json url,isDraft,mergeable,statusCheckRollup
```

Expected:
- `Python checks` passes and is now backed by `.\scripts\check.ps1 -GuiSmoke -Build`.
- `CPU ML extra resolves` passes and includes `scripts/ml_import_smoke.py`.
- PR #6 remains mergeable.
