# PitchStems Audit Repair Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the six remaining June 7, 2026 audit findings with small, reviewable changes that keep the PySide app usable and pass targeted checks plus `.\scripts\check.ps1`.

**Architecture:** Land the lifecycle fixes first because they affect user-visible shutdown behavior. Then add low-cost quality gates and ML dependency validation. Continue modularization as behavior-preserving extractions behind the current PySide surface.

**Tech Stack:** Python 3.10, PySide6, pytest, Ruff, PowerShell, GitHub Actions, mypy, pytest-cov.

---

## File Structure

- Modify: `src/pitchstems/gui_processing.py`
  - Finish worker state before deferred close retries and remove unused cancellation helper.
- Modify: `src/pitchstems/gui_shutdown.py`
  - Own the close-triggered cancellation message and make close policy robust after worker completion.
- Modify: `tests/test_gui_processing.py`
  - Add a regression test for the deferred-close race through the real shutdown policy.
- Modify: `tests/test_gui_shutdown.py`
  - Assert the canonical cancellation message and completed-worker close behavior.
- Create: `docs/architecture/native-job-cancellation.md`
  - Record the current cooperative boundary and the future process-based job strategy.
- Create: `.github/workflows/ml-dependencies.yml`
  - Validate CPU ML extra dependency resolution when dependency files change, on schedule, and by manual dispatch.
- Modify: `pyproject.toml`
  - Add scoped type and coverage tooling/configuration.
- Modify: `scripts/check.ps1`
  - Run scoped type checks and scoped coverage checks before compile/package validation.
- Create: `tests/test_editor_models.py`
  - Cover the small shared model properties used by chord/scale/editor modules.
- Create: `src/pitchstems/gui_harmony_dialogs.py`
  - Move harmony report dialog construction out of `MainWindow`.
- Modify: `src/pitchstems/app.py`
  - Replace inline harmony dialog bodies with thin delegates.

---

### Task 1: Fix Deferred Close And Cancellation Message

**Files:**
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `src/pitchstems/gui_shutdown.py`
- Modify: `tests/test_gui_processing.py`
- Modify: `tests/test_gui_shutdown.py`

- [ ] **Step 1: Add the failing deferred-close regression test**

In `tests/test_gui_processing.py`, import the shutdown module and add the live worker fake plus close path:

```python
import pitchstems.gui_shutdown as gui_shutdown
```

Add these helpers near `_FlushWindow`:

```python
class _LiveWorker:
    def is_alive(self) -> bool:
        return True
```

Extend `_FlushWindow.__init__` with:

```python
        self.worker = _LiveWorker()
        self.close_after_worker = False
        self.closed = False
        self.close_attempts = 0
```

Add this method to `_FlushWindow`:

```python
    def close(self) -> None:
        self.close_attempts += 1
        if gui_shutdown.request_window_close(self):
            self.closed = True
```

Add the regression test:

```python
def test_flush_messages_allows_deferred_close_after_worker_completion() -> None:
    window = _FlushWindow()
    window.close_after_worker = True
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.close_attempts == 1
    assert window.closed is True
    assert window.close_after_worker is False
    assert window.worker_jobs.active_token is None
```

- [ ] **Step 2: Run the regression test and verify it fails**

Run:

```powershell
py -3.10 -m pytest tests/test_gui_processing.py::test_flush_messages_allows_deferred_close_after_worker_completion -q
```

Expected: FAIL because `flush_messages()` clears `close_after_worker`, calls `window.close()`, and `request_window_close()` still sees a live worker object.

- [ ] **Step 3: Make completed workers closable before retrying close**

In `src/pitchstems/gui_processing.py`, remove the unused `request_worker_cancel()` function:

```python
def request_worker_cancel(window) -> bool:
    if not window.worker_jobs.cancel():
        return False
    window.set_activity_message("Cancelling after the current model stage...")
    return True
```

In the `ENABLE_PROCESS` branch of `flush_messages()`, replace the deferred-close block with:

```python
                if getattr(window, "close_after_worker", False):
                    window.close_after_worker = False
                    window.worker = None
                    window.close()
```

This is safe at this point because the worker has already posted its terminal completion message from the `finally` block.

- [ ] **Step 4: Centralize the close-triggered cancellation message**

In `src/pitchstems/gui_shutdown.py`, add a module constant and helper:

```python
CANCELLING_AFTER_STAGE_MESSAGE = "Cancelling after the current model stage..."


def request_worker_cancel(window) -> bool:
    if not window.worker_jobs.cancel():
        return False
    window.set_activity_message(CANCELLING_AFTER_STAGE_MESSAGE)
    return True
```

Change `request_window_close()` to use the helper:

```python
def request_window_close(window) -> bool:
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        return True
    if request_worker_cancel(window):
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
    return False
```

- [ ] **Step 5: Update shutdown tests for the canonical message**

In `tests/test_gui_shutdown.py`, change the final assertion in `test_request_window_close_cancels_active_worker_and_defers_close()` to:

```python
    assert window.activities[-1] == "Cancelling after the current model stage..."
```

Add a completed-worker policy test:

```python
def test_request_window_close_allows_close_when_worker_state_is_retired() -> None:
    window = _Window(alive=True)
    window.worker = None

    assert request_window_close(window) is True
```

- [ ] **Step 6: Run targeted GUI lifecycle tests**

Run:

```powershell
py -3.10 -m pytest tests/test_gui_processing.py tests/test_gui_shutdown.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the lifecycle fix**

Run:

```powershell
git add src/pitchstems/gui_processing.py src/pitchstems/gui_shutdown.py tests/test_gui_processing.py tests/test_gui_shutdown.py
git commit -m "fix: harden deferred worker close"
```

---

### Task 2: Document Native Cancellation Boundary

**Files:**
- Create: `docs/architecture/native-job-cancellation.md`
- Modify: `README.md`

- [ ] **Step 1: Add the architecture note**

Create `docs/architecture/native-job-cancellation.md`:

```markdown
# Native Job Cancellation

PitchStems cancellation is cooperative in the Python orchestration layer. The app checks cancellation before and after expensive native model stages, but it does not interrupt BS-RoFormer or Basic Pitch once those libraries are executing.

## Current Boundary

- `process_audio_file()` can stop between copy, normalization, separation, MIDI, and archive stages.
- `process_midi_from_stems()` can stop between stem transcriptions and before replacement of previous MIDI outputs.
- `separate_stems()` and `transcribe_to_midi()` are treated as native calls that either return, raise, or finish through their library-level behavior.

## User-Facing Behavior

When the user closes the app during processing, PitchStems requests cancellation, waits for the current model stage to finish, and then closes. This avoids corrupting project folders or leaving half-written replacement MIDI.

## Future Process-Based Strategy

The next architecture should run ML work in a separate job process or sidecar. Each job should have a stable `job_id`, emit progress events, write outputs into a staging directory, and promote outputs only after success. Cancellation can then terminate the process, delete the staging directory, and leave the existing project unchanged.

## Non-Goals

- Do not kill Python threads inside the current PySide process.
- Do not terminate model libraries mid-write without a staging boundary.
- Do not change existing `.pitchstems` project compatibility for cancellation alone.
```

- [ ] **Step 2: Link the note from the README**

In `README.md`, near the existing cancellation paragraph, add:

```markdown
For the technical boundary and future process-based cancellation strategy, see `docs/architecture/native-job-cancellation.md`.
```

- [ ] **Step 3: Verify docs are referenced**

Run:

```powershell
rg -n "native-job-cancellation|current model stage|cooperative" README.md docs/architecture/native-job-cancellation.md
```

Expected: both the README link and the architecture note are found.

- [ ] **Step 4: Commit the cancellation documentation**

Run:

```powershell
git add README.md docs/architecture/native-job-cancellation.md
git commit -m "docs: record native cancellation boundary"
```

---

### Task 3: Add Scoped Quality Gates

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/check.ps1`
- Create: `tests/test_editor_models.py`

- [ ] **Step 1: Add focused editor model tests**

Create `tests/test_editor_models.py`:

```python
from __future__ import annotations

from pitchstems.editor_models import ChordRegion, NoteEvent


def test_note_event_duration_never_negative() -> None:
    assert NoteEvent("piano", 2.0, 1.25, 60, 90).duration == 0.0
    assert NoteEvent("piano", 1.25, 2.0, 60, 90).duration == 0.75


def test_chord_region_duration_never_negative() -> None:
    assert ChordRegion(3.0, 2.0, "C", 0.8).duration == 0.0
    assert ChordRegion(2.0, 3.5, "C", 0.8).duration == 1.5


def test_note_event_name_uses_default_notation() -> None:
    assert NoteEvent("piano", 0.0, 1.0, 60, 90).name == "C4"
```

- [ ] **Step 2: Add type and coverage tooling**

In `pyproject.toml`, replace the `dev` extra with:

```toml
dev = [
  "build>=1.2",
  "mypy>=1.15",
  "pytest>=8.0",
  "pytest-cov>=6.0",
  "ruff>=0.6",
]
```

Add scoped mypy configuration:

```toml
[tool.mypy]
python_version = "3.10"
files = [
  "src/pitchstems/editor_models.py",
  "src/pitchstems/gui_jobs.py",
]
warn_unused_configs = true
disallow_untyped_defs = true
check_untyped_defs = true
no_implicit_optional = true
```

Add scoped coverage configuration:

```toml
[tool.coverage.run]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = true
```

- [ ] **Step 3: Add the checks to `scripts/check.ps1`**

After the Ruff invocation, add:

```powershell
Invoke-Checked "Running mypy..." { & $python @pythonArgs -m mypy }
```

Replace the existing pytest invocation with:

```powershell
Invoke-Checked "Running tests..." {
    & $python @pythonArgs -m pytest `
        --cov=pitchstems.editor_models `
        --cov=pitchstems.gui_jobs `
        --cov-report=term-missing `
        --cov-fail-under=90
}
```

- [ ] **Step 4: Install updated dev tools locally if needed**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,gui]"
```

Expected: `mypy` and `pytest-cov` install successfully.

- [ ] **Step 5: Run scoped checks**

Run:

```powershell
.\scripts\check.ps1
```

Expected: Ruff, mypy, pytest with scoped coverage, compileall, pip check, and doctor pass.

- [ ] **Step 6: Commit quality gates**

Run:

```powershell
git add pyproject.toml scripts/check.ps1 tests/test_editor_models.py
git commit -m "test: add scoped quality gates"
```

---

### Task 4: Add ML Dependency Resolution Workflow

**Files:**
- Create: `.github/workflows/ml-dependencies.yml`

- [ ] **Step 1: Add dependency workflow**

Create `.github/workflows/ml-dependencies.yml`:

```yaml
name: ML Dependencies

on:
  pull_request:
    branches: [main]
    paths:
      - "pyproject.toml"
      - ".github/workflows/ml-dependencies.yml"
  workflow_dispatch:
  schedule:
    - cron: "17 6 * * 1"

permissions:
  contents: read

jobs:
  cpu-extra-resolve:
    name: CPU ML extra resolves
    runs-on: windows-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.10"
          cache: pip

      - name: Install CPU ML extra
        run: |
          python -m pip install -U pip
          python -m pip install -e ".[cpu]"

      - name: Check installed metadata
        run: python -m pip check
```

- [ ] **Step 2: Validate workflow syntax and repo checks**

Run:

```powershell
git diff --check
.\scripts\check.ps1
```

Expected: whitespace check and local project check pass.

- [ ] **Step 3: Commit ML dependency workflow**

Run:

```powershell
git add .github/workflows/ml-dependencies.yml
git commit -m "ci: validate ML dependency resolution"
```

---

### Task 5: Extract Harmony Dialogs From MainWindow

**Files:**
- Create: `src/pitchstems/gui_harmony_dialogs.py`
- Modify: `src/pitchstems/app.py`

- [ ] **Step 1: Create the dialog helper module**

Create `src/pitchstems/gui_harmony_dialogs.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from pitchstems.chord_gap_analysis import chord_gap_report
from pitchstems.harmony_report import current_chord_analysis_report
from pitchstems.scale_analysis import theory_analysis_report


def show_report_dialog(parent, title: str, report: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout()
    text = QTextEdit()
    text.setReadOnly(True)
    text.setPlainText(report)
    layout.addWidget(text)
    close_button = QPushButton("Close")
    close_button.clicked.connect(dialog.accept)
    button_row = QHBoxLayout()
    button_row.addStretch(1)
    button_row.addWidget(close_button)
    layout.addLayout(button_row)
    dialog.setLayout(layout)
    dialog.resize(820, 680)
    dialog.exec()


def inspect_current_chord_analysis(window) -> None:
    if window.editor_project is None:
        return
    show_report_dialog(
        window,
        "Harmony Inspector Calculation",
        current_chord_analysis_report(window),
    )


def inspect_current_theory_analysis(window) -> None:
    if window.current_theory_analysis is None:
        return
    show_report_dialog(
        window,
        "Theory Inspector Calculation",
        theory_analysis_report(window.current_theory_analysis),
    )


def inspect_current_gap_suggestions(window) -> None:
    if window.current_chord_gap_analysis is None:
        return
    show_report_dialog(
        window,
        "Chord Gap Suggestions",
        chord_gap_report(window.current_chord_gap_analysis),
    )
```

- [ ] **Step 2: Delegate from `MainWindow`**

In `src/pitchstems/app.py`, add:

```python
from pitchstems import gui_harmony_dialogs
```

Replace the bodies of `inspect_current_chord_analysis()`, `inspect_current_theory_analysis()`, and `inspect_current_gap_suggestions()` with:

```python
            gui_harmony_dialogs.inspect_current_chord_analysis(self)
```

```python
            gui_harmony_dialogs.inspect_current_theory_analysis(self)
```

```python
            gui_harmony_dialogs.inspect_current_gap_suggestions(self)
```

Keep `current_chord_analysis_report()` in `MainWindow` only if another caller still uses it after the import cleanup.

- [ ] **Step 3: Remove now-unused imports from `app.py`**

Remove these imports from `src/pitchstems/app.py` when Ruff reports them unused:

```python
from pitchstems.harmony_report import current_chord_analysis_report as build_chord_analysis_report
from pitchstems.scale_analysis import theory_analysis_report
from pitchstems.chord_gap_analysis import chord_gap_report
```

If `current_chord_analysis_report()` remains as a compatibility method, keep only:

```python
from pitchstems.harmony_report import current_chord_analysis_report as build_chord_analysis_report
```

- [ ] **Step 4: Verify extraction**

Run:

```powershell
py -3.10 -m ruff check src tests
py -3.10 -m pytest -q
.\scripts\check.ps1 -GuiSmoke
```

Expected: Ruff, tests, and GUI smoke pass.

- [ ] **Step 5: Commit harmony extraction**

Run:

```powershell
git add src/pitchstems/app.py src/pitchstems/gui_harmony_dialogs.py
git commit -m "refactor: extract harmony dialogs"
```

---

### Task 6: Plan Next Module Extractions As Separate Work

**Files:**
- Modify: `docs/architecture/product-architecture.md`

- [ ] **Step 1: Add an extraction backlog table**

In `docs/architecture/product-architecture.md`, after the existing “Before adding new editor UI behavior” list, add:

```markdown
## Extraction Backlog

| Slice | First file to create | Source pressure | Verification |
| --- | --- | --- | --- |
| Harmony dialogs | `src/pitchstems/gui_harmony_dialogs.py` | `MainWindow` owns report dialog construction | `.\scripts\check.ps1 -GuiSmoke` |
| Timeline chord geometry | `src/pitchstems/timeline_chord_geometry.py` | `TimelineView` mixes drag math with scene updates | focused geometry tests plus `.\scripts\check.ps1` |
| Chord naming | `src/pitchstems/chord_naming.py` | `chord_analysis.py` mixes naming with scoring and detection | existing chord analysis tests plus new naming tests |
| Chord scoring | `src/pitchstems/chord_scoring.py` | scoring weights and evidence are embedded in detection flow | existing chord analysis tests plus scoring fixture tests |
| Chord detection facade | `src/pitchstems/chord_detection.py` | compatibility API should survive internal splits | full test suite and import compatibility checks |
```

- [ ] **Step 2: Verify docs and commit**

Run:

```powershell
rg -n "Extraction Backlog|timeline_chord_geometry|chord_naming|chord_scoring|chord_detection" docs/architecture/product-architecture.md
git add docs/architecture/product-architecture.md
git commit -m "docs: define extraction backlog"
```

Expected: the backlog rows are found and committed.

---

### Task 7: Final Verification And PR Update

**Files:**
- No source file changes beyond previous tasks.

- [ ] **Step 1: Run full local verification**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
git diff --check main...HEAD
```

Expected: all checks pass.

- [ ] **Step 2: Inspect branch state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -8
```

Expected: working tree is clean and the new commits are visible on the repair branch.

- [ ] **Step 3: Push and update PR**

Run:

```powershell
git push
gh pr view 6 --json url,isDraft,mergeable,statusCheckRollup
```

Expected: PR #6 remains open, draft until intentionally marked ready, mergeable or awaiting GitHub refresh, and checks pass after GitHub completes.
