# GUI Responsiveness And Input Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent bad input from failing late and keep playback/scrubbing responsive on large editor projects.

**Architecture:** Add early local-file audio validation and introduce a small harmony refresh scheduler that throttles expensive analysis while playback is moving. Use pure helper functions where possible so behavior is testable without a full Qt scene.

**Tech Stack:** PySide6, pathlib, QTimer, pytest.

---

## Files

- Create: `src/pitchstems/input_validation.py`
- Modify: `src/pitchstems/gui_widgets.py`
- Modify: `src/pitchstems/gui_project_flow.py`
- Modify: `src/pitchstems/app.py`
- Modify: `src/pitchstems/gui_transport_flow.py`
- Modify: `src/pitchstems/gui_harmony_flow.py`
- Test: `tests/test_file_opening.py`
- Test: `tests/test_gui_processing.py`
- Test: `tests/test_harmony_inspector.py`

## Task 1: Validate Audio Paths Early

- [ ] **Step 1: Write failing tests**

Create `tests/test_input_validation.py`:

```python
from __future__ import annotations

from pathlib import Path

from pitchstems.input_validation import validate_audio_input


def test_validate_audio_input_rejects_directory(tmp_path: Path) -> None:
    error = validate_audio_input(tmp_path)
    assert error == "Choose an audio file, not a folder."


def test_validate_audio_input_rejects_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not audio", encoding="utf-8")
    assert "Unsupported audio file type" in validate_audio_input(path)


def test_validate_audio_input_accepts_common_audio_suffix(tmp_path: Path) -> None:
    path = tmp_path / "song.wav"
    path.write_bytes(b"RIFF")
    assert validate_audio_input(path) is None
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_input_validation.py -q`

Expected: FAIL because `input_validation.py` does not exist.

- [ ] **Step 2: Implement validator**

Create `src/pitchstems/input_validation.py`:

```python
from __future__ import annotations

from pathlib import Path

SUPPORTED_AUDIO_SUFFIXES = {
    ".aac", ".aiff", ".aif", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma",
}


def validate_audio_input(path: Path) -> str | None:
    if not path.exists():
        return f"Audio file does not exist: {path}"
    if not path.is_file():
        return "Choose an audio file, not a folder."
    if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        return f"Unsupported audio file type: {path.suffix or '(none)'}"
    return None
```

- [ ] **Step 3: Wire drag/drop and open file flows**

In `src/pitchstems/gui_widgets.py`, reject non-local URLs and invalid file paths before setting `DropZone.path`.

In `src/pitchstems/gui_project_flow.py`, after dialog selection:

```python
error = validate_audio_input(path)
if error:
    window.append_log(error)
    window.statusBar().showMessage(error, 5000)
    return
```

In `src/pitchstems/gui_processing.py`, before starting a full run:

```python
error = validate_audio_input(window.drop_zone.path)
if error:
    window.append_log(error)
    return
```

- [ ] **Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_input_validation.py tests/test_file_opening.py tests/test_gui_processing.py -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 2: Add Harmony Refresh Throttle

- [ ] **Step 1: Write failing scheduler tests**

Create `tests/test_harmony_refresh.py`:

```python
from __future__ import annotations

from pitchstems.gui_harmony_flow import HarmonyRefreshGate


def test_harmony_refresh_gate_allows_initial_and_throttles_close_updates() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert not gate.should_refresh(10.1, now_seconds=1.10)
    assert gate.should_refresh(10.2, now_seconds=1.26)


def test_harmony_refresh_gate_forces_selection_changes() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert gate.should_refresh(10.0, now_seconds=1.05, force=True)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_harmony_refresh.py -q`

Expected: FAIL.

- [ ] **Step 2: Implement gate**

In `src/pitchstems/gui_harmony_flow.py`:

```python
from dataclasses import dataclass


@dataclass
class HarmonyRefreshGate:
    min_interval_seconds: float = 0.25
    last_refresh_seconds: float | None = None

    def should_refresh(self, position_seconds: float, now_seconds: float, force: bool = False) -> bool:
        if force or self.last_refresh_seconds is None:
            self.last_refresh_seconds = now_seconds
            return True
        if now_seconds - self.last_refresh_seconds >= self.min_interval_seconds:
            self.last_refresh_seconds = now_seconds
            return True
        return False
```

- [ ] **Step 3: Use gate during transport updates**

In `src/pitchstems/app.py`, initialize:

```python
self.harmony_refresh_gate = gui_harmony_flow.HarmonyRefreshGate()
```

In `set_editor_position_seconds()` or the method that calls `refresh_current_harmony()`, only refresh when:

```python
if self.harmony_refresh_gate.should_refresh(seconds, time.monotonic(), force=force_harmony_refresh):
    self.refresh_current_harmony(seconds)
```

Force refresh for manual chord edits, selection changes, note filter changes, and notation changes.

- [ ] **Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_harmony_refresh.py tests/test_gui_transport.py tests/test_harmony_inspector.py -q
.\scripts\check.ps1 -GuiSmoke
```

Expected: PASS.

## Task 3: Commit Responsiveness Work

- [ ] **Step 1: Review diff**

Run: `git diff -- src tests`

Expected: only validation and harmony refresh gating changed.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src\pitchstems\input_validation.py src\pitchstems\gui_widgets.py src\pitchstems\gui_project_flow.py src\pitchstems\gui_processing.py src\pitchstems\app.py src\pitchstems\gui_transport_flow.py src\pitchstems\gui_harmony_flow.py tests\test_input_validation.py tests\test_harmony_refresh.py tests\test_file_opening.py tests\test_gui_processing.py tests\test_harmony_inspector.py
git commit -m "fix: validate audio input and throttle harmony refresh"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers bad file drops, late processing failures, and synchronous harmony refresh pressure.
- Placeholder scan: exact validator and gate contracts are defined.
- Type consistency: `HarmonyRefreshGate` is the only throttle type.
