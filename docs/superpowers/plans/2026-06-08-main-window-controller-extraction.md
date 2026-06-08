# Main Window Controller Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `MainWindow` coupling by moving stable UI state decisions into typed modules while preserving current PySide behavior.

**Architecture:** Extract pure state/model helpers first, then delegate from `app.py` without changing visible behavior. Avoid moving Qt widget construction until tests prove the extracted state contracts.

**Tech Stack:** Python 3.10, PySide6, dataclasses, pytest, mypy.

---

## File Structure

- Create: `src/pitchstems/gui_pipeline_model.py` for pipeline button/settings state decisions.
- Create: `src/pitchstems/gui_editor_model.py` for editor state summaries and layout-independent state decisions.
- Modify: `src/pitchstems/gui_pipeline_state.py` to consume `PipelinePageModel`.
- Modify: `src/pitchstems/gui_editor_load.py` and `src/pitchstems/gui_editor_state.py` to consume editor model helpers where stable.
- Modify: `src/pitchstems/app.py` only to delegate; do not add new domain logic.
- Modify: `pyproject.toml` to add the new small modules to mypy.
- Test: `tests/test_gui_pipeline_model.py`, `tests/test_gui_editor_model.py`, and existing GUI tests.

### Task 1: Extract Pipeline State Model

**Files:**
- Create: `src/pitchstems/gui_pipeline_model.py`
- Test: `tests/test_gui_pipeline_model.py`

- [ ] **Step 1: Write failing tests**

```python
from pitchstems.gui_pipeline_model import PipelinePageModel


def test_pipeline_page_model_disables_run_controls_while_busy() -> None:
    model = PipelinePageModel(busy=True, has_result=True, generate_midi=True)

    assert model.drop_zone_enabled is False
    assert model.run_full_enabled is False
    assert model.run_midi_enabled is False
    assert model.cancel_enabled is True
    assert model.midi_stem_checks_enabled is False


def test_pipeline_page_model_enables_midi_rerun_only_with_result() -> None:
    model = PipelinePageModel(busy=False, has_result=True, generate_midi=True)

    assert model.drop_zone_enabled is True
    assert model.run_full_enabled is True
    assert model.run_midi_enabled is True
    assert model.cancel_enabled is False
    assert model.midi_stem_checks_enabled is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_pipeline_model.py -q`
Expected: FAIL because `pitchstems.gui_pipeline_model` does not exist.

- [ ] **Step 3: Implement model**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelinePageModel:
    busy: bool
    has_result: bool
    generate_midi: bool

    @property
    def drop_zone_enabled(self) -> bool:
        return not self.busy

    @property
    def run_full_enabled(self) -> bool:
        return not self.busy

    @property
    def run_midi_enabled(self) -> bool:
        return (not self.busy) and self.has_result

    @property
    def cancel_enabled(self) -> bool:
        return self.busy

    @property
    def settings_enabled(self) -> bool:
        return not self.busy

    @property
    def midi_stem_checks_enabled(self) -> bool:
        return (not self.busy) and self.generate_midi
```

- [ ] **Step 4: Verify tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_pipeline_model.py -q`
Expected: PASS.

### Task 2: Delegate Pipeline Widget State

**Files:**
- Modify: `src/pitchstems/gui_pipeline_state.py`
- Test: `tests/test_gui_processing.py`, `tests/test_gui_pipeline_model.py`

- [ ] **Step 1: Replace inline booleans with model**

In `set_processing_state`, construct:

```python
from pitchstems.gui_pipeline_model import PipelinePageModel

model = PipelinePageModel(
    busy=busy,
    has_result=window.current_result is not None,
    generate_midi=window.generate_midi.isChecked(),
)
```

Then set widgets from the model:

```python
window.drop_zone.setEnabled(model.drop_zone_enabled)
window.run_full.setEnabled(model.run_full_enabled)
window.run_midi.setEnabled(model.run_midi_enabled)
window.cancel_button.setEnabled(model.cancel_enabled)
window.stem.setEnabled(model.settings_enabled)
window.bs_device.setEnabled(model.settings_enabled)
window.generate_midi.setEnabled(model.settings_enabled)
for checkbox in window.midi_stem_checks.values():
    checkbox.setEnabled(model.midi_stem_checks_enabled)
```

- [ ] **Step 2: Verify GUI processing behavior**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py tests/test_gui_pipeline_model.py -q`
Expected: PASS.

### Task 3: Extract Editor State Summary Helpers

**Files:**
- Create: `src/pitchstems/gui_editor_model.py`
- Test: `tests/test_gui_editor_model.py`

- [ ] **Step 1: Write failing tests**

```python
from pitchstems.gui_editor_model import EditorSummaryModel


def test_editor_summary_model_empty_project() -> None:
    model = EditorSummaryModel(track_count=0, note_count=0, duration_seconds=0.0)

    assert model.has_timeline is False
    assert model.fit_song_enabled is False
    assert model.summary == "Run separation + MIDI to build an editor timeline."


def test_editor_summary_model_loaded_project() -> None:
    model = EditorSummaryModel(track_count=2, note_count=150, duration_seconds=92.4)

    assert model.has_timeline is True
    assert model.fit_song_enabled is True
    assert "2 tracks" in model.summary
    assert "150 notes" in model.summary
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_editor_model.py -q`
Expected: FAIL because `pitchstems.gui_editor_model` does not exist.

- [ ] **Step 3: Implement helper**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditorSummaryModel:
    track_count: int
    note_count: int
    duration_seconds: float

    @property
    def has_timeline(self) -> bool:
        return self.track_count > 0 or self.note_count > 0 or self.duration_seconds > 0

    @property
    def fit_song_enabled(self) -> bool:
        return self.has_timeline

    @property
    def summary(self) -> str:
        if not self.has_timeline:
            return "Run separation + MIDI to build an editor timeline."
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"Editor timeline: {self.track_count} tracks, {self.note_count} notes, {minutes}:{seconds:02d}."
```

- [ ] **Step 4: Verify tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_editor_model.py -q`
Expected: PASS.

### Task 4: Add New Modules To Strict Typing

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add mypy files**

Add these entries under `[tool.mypy].files`:

```toml
  "src/pitchstems/gui_editor_model.py",
  "src/pitchstems/gui_pipeline_model.py",
```

- [ ] **Step 2: Run focused gate**

Run: `.\scripts\check.ps1`
Expected: Ruff, mypy, tests, compileall, pip check, and doctor pass.

### Task 5: Review And Commit

- [ ] **Step 1: Inspect diff**

Run: `git diff -- src/pitchstems/gui_pipeline_model.py src/pitchstems/gui_editor_model.py src/pitchstems/gui_pipeline_state.py pyproject.toml tests/test_gui_pipeline_model.py tests/test_gui_editor_model.py`
Expected: Diff only contains the planned extraction and tests.

- [ ] **Step 2: Commit**

```powershell
git add src/pitchstems/gui_pipeline_model.py src/pitchstems/gui_editor_model.py src/pitchstems/gui_pipeline_state.py pyproject.toml tests/test_gui_pipeline_model.py tests/test_gui_editor_model.py
git commit -m "refactor: extract stable gui state models"
```

## Self-Review

- Spec coverage: covers the `MainWindow` centralization finding with low-risk typed seams.
- Placeholder scan: every new symbol is defined in this plan before use.
- Type consistency: `PipelinePageModel` and `EditorSummaryModel` are the only new public contracts.
