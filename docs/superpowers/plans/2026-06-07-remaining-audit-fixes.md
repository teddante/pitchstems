# Remaining Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining PitchStems audit findings: safe GUI shutdown during active work, accurate success/cancel/error completion state, clearer native-call cancellation boundaries, and staged extraction of the largest GUI/music-analysis modules.

**Architecture:** First repair the user-visible lifecycle bugs around worker completion and close handling with TDD. Then make cancellation state explicit so a cancel request stays visible until the worker reports back. Finally, reduce future refactor risk by extracting neutral model types and documenting module split checkpoints without destabilizing the working PySide app.

**Tech Stack:** Python 3.10, PySide6, pytest, Ruff, PowerShell project checks, current `src/pitchstems` package layout.

---

### Task 1: Distinguish Success, Cancel, And Error Completion

**Files:**
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `tests/test_gui_processing.py`

- [ ] **Step 1: Write failing tests for final UI state**

Append these tests to `tests/test_gui_processing.py`:

```python
from pitchstems.gui_jobs import WorkerJobState


class _FlushWindow:
    def __init__(self) -> None:
        self.logger = _Logger()
        self.messages: queue.Queue[object] = queue.Queue()
        self.worker_jobs = WorkerJobState()
        self.worker_jobs.active_token = 7
        self.results: list[PipelineResult] = []
        self.logs: list[str] = []
        self.processing_states: list[bool] = []
        self.activity_messages: list[str] = []

    def is_active_worker_token(self, token: int) -> bool:
        return self.worker_jobs.is_active(token)

    def set_current_result(self, result: PipelineResult) -> None:
        self.results.append(result)

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def set_activity_message(self, message: str) -> None:
        self.activity_messages.append(message)

    def set_processing_state(self, busy: bool) -> None:
        self.processing_states.append(busy)

    def end_activity(self, message: str = "Ready") -> None:
        self.activity_messages.append(message)


def test_flush_messages_reports_cancelled_completion_without_success_text(tmp_path: Path) -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Processing cancelled."))
    window.messages.put(("ENABLE_PROCESS", 7, "cancelled"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Processing cancelled."]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing cancelled"
    assert window.worker_jobs.active_token is None


def test_flush_messages_reports_error_completion_without_success_text(tmp_path: Path) -> None:
    window = _FlushWindow()
    window.messages.put(("WORKER_LOG", 7, "Error: boom"))
    window.messages.put(("ENABLE_PROCESS", 7, "error"))

    gui_processing.flush_messages(window)

    assert window.logs == ["Error: boom"]
    assert window.processing_states == [False]
    assert window.activity_messages[-1] == "Processing failed"
    assert window.worker_jobs.active_token is None
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py -q
```

Expected before implementation: FAIL because `flush_messages` treats `ENABLE_PROCESS` as a two-item tuple and always ends with `Processing complete`.

- [ ] **Step 3: Send completion status from worker runners**

In `src/pitchstems/gui_processing.py`, update `run_full_pipeline` and `run_midi_stage` so they enqueue a status-specific completion tuple:

```python
def run_full_pipeline(window, token: int, request: FullRunRequest) -> None:
    completion = "success"
    try:
        window.logger.info("Starting full pipeline for %s", request.input_path)
        result = process_audio_file(
            request.input_path,
            request.output_root,
            separation_options=request.separation_options,
            generate_midi=request.generate_midi,
            midi_policy="all",
            midi_options=request.midi_options,
            midi_stems=request.midi_stems,
            create_zip=request.create_zip,
            log=lambda message: window.messages.put(("WORKER_LOG", token, message)),
            cancelled=request.cancelled,
        )
        window.messages.put(("RESULT", token, result))
        window.messages.put(("WORKER_LOG", token, f"Project ready: {result.project_dir}"))
    except PipelineCancelledError:
        completion = "cancelled"
        window.logger.info("Processing cancelled")
        window.messages.put(("WORKER_LOG", token, "Processing cancelled."))
    except Exception as exc:
        completion = "error"
        window.logger.exception("Full pipeline failed")
        window.messages.put(("WORKER_LOG", token, f"Error: {exc}"))
    finally:
        window.messages.put(("ENABLE_PROCESS", token, completion))
```

Apply the same `completion = "success"`, `"cancelled"`, and `"error"` pattern to `run_midi_stage`.

- [ ] **Step 4: Read status in message flushing**

In `flush_messages`, replace the `ENABLE_PROCESS` block with:

```python
        elif isinstance(message, tuple) and message[0] == "ENABLE_PROCESS":
            _kind, token, *status_parts = message
            status = str(status_parts[0]) if status_parts else "success"
            if window.is_active_worker_token(int(token)):
                window.worker_jobs.active_token = None
                window.set_processing_state(False)
                if status == "cancelled":
                    window.end_activity("Processing cancelled")
                elif status == "error":
                    window.end_activity("Processing failed")
                else:
                    window.end_activity("Processing complete")
            else:
                window.logger.info("Ignored stale worker completion for token %s", token)
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py -q
```

Expected after implementation: all `test_gui_processing.py` tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/gui_processing.py tests/test_gui_processing.py
git commit -m "fix: report worker completion status accurately"
```

---

### Task 2: Keep Cancellation Requests Visible Until Worker Completion

**Files:**
- Modify: `src/pitchstems/gui_jobs.py`
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `tests/test_gui_jobs.py`
- Modify: `tests/test_gui_processing.py`

- [ ] **Step 1: Write failing job-state tests**

Append this test to `tests/test_gui_jobs.py`:

```python
def test_worker_job_state_tracks_cancel_request_without_clearing_active_token() -> None:
    state = WorkerJobState()
    token = state.start()

    assert state.request_cancel(token) is True
    assert state.active_token == token
    assert state.is_cancel_requested(token)

    state.finish(token)

    assert state.active_token is None
    assert not state.is_cancel_requested(token)
```

- [ ] **Step 2: Run job-state tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py -q
```

Expected before implementation: FAIL because `WorkerJobState` has no `request_cancel`, `is_cancel_requested`, or `finish`.

- [ ] **Step 3: Implement explicit cancel state**

Update `src/pitchstems/gui_jobs.py`:

```python
@dataclass
class WorkerJobState:
    next_token: int = 0
    active_token: int | None = None
    cancel_requested_token: int | None = None

    def start(self) -> int:
        self.next_token += 1
        self.active_token = self.next_token
        self.cancel_requested_token = None
        return self.next_token

    def cancel(self) -> bool:
        if self.active_token is None:
            return False
        self.cancel_requested_token = self.active_token
        return True

    def request_cancel(self, token: int) -> bool:
        if self.active_token != token:
            return False
        self.cancel_requested_token = token
        return True

    def is_cancel_requested(self, token: int) -> bool:
        return self.cancel_requested_token == token

    def finish(self, token: int) -> None:
        if self.active_token == token:
            self.active_token = None
        if self.cancel_requested_token == token:
            self.cancel_requested_token = None

    def invalidate(self) -> bool:
        had_active = self.active_token is not None
        self.next_token += 1
        self.active_token = None
        self.cancel_requested_token = None
        return had_active

    def is_active(self, token: int) -> bool:
        return self.active_token == token
```

- [ ] **Step 4: Use cancel state in worker requests**

In `start_full_processing` and `start_midi_processing`, change the cancellation callback:

```python
cancelled=lambda token=token: window.worker_jobs.is_cancel_requested(token),
```

Keep `invalidate_worker_token(window)` for stale project-switch invalidation. Add this helper to `gui_processing.py`:

```python
def request_worker_cancel(window) -> bool:
    return window.worker_jobs.cancel()
```

In the `ENABLE_PROCESS` block from Task 1, replace direct active-token clearing with:

```python
                window.worker_jobs.finish(int(token))
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py tests/test_gui_processing.py -q
```

Expected: all GUI job and GUI processing tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/gui_jobs.py src/pitchstems/gui_processing.py tests/test_gui_jobs.py tests/test_gui_processing.py
git commit -m "fix: track worker cancellation requests explicitly"
```

---

### Task 3: Safe GUI Shutdown During Active Work

**Files:**
- Create: `src/pitchstems/gui_shutdown.py`
- Modify: `src/pitchstems/app.py`
- Create: `tests/test_gui_shutdown.py`

- [ ] **Step 1: Write failing shutdown-policy tests**

Create `tests/test_gui_shutdown.py`:

```python
from __future__ import annotations

from pitchstems.gui_jobs import WorkerJobState
from pitchstems.gui_shutdown import request_window_close


class _Worker:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


class _Window:
    def __init__(self, alive: bool) -> None:
        self.worker = _Worker(alive)
        self.worker_jobs = WorkerJobState()
        self.worker_jobs.start()
        self.logs: list[str] = []
        self.activities: list[str] = []
        self.close_after_worker = False

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def set_activity_message(self, message: str) -> None:
        self.activities.append(message)


def test_request_window_close_allows_close_when_no_worker_is_alive() -> None:
    window = _Window(alive=False)

    assert request_window_close(window) is True
    assert not window.close_after_worker


def test_request_window_close_cancels_active_worker_and_defers_close() -> None:
    window = _Window(alive=True)

    assert request_window_close(window) is False
    assert window.worker_jobs.is_cancel_requested(1)
    assert window.close_after_worker
    assert window.activities[-1] == "Cancelling active work before closing..."
```

- [ ] **Step 2: Run shutdown tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_shutdown.py -q
```

Expected before implementation: FAIL because `pitchstems.gui_shutdown` does not exist.

- [ ] **Step 3: Implement shutdown policy**

Create `src/pitchstems/gui_shutdown.py`:

```python
from __future__ import annotations


def request_window_close(window) -> bool:
    worker = getattr(window, "worker", None)
    if worker is None or not worker.is_alive():
        return True
    if window.worker_jobs.cancel():
        window.close_after_worker = True
        window.append_log("Close requested; cancelling active processing first.")
        window.set_activity_message("Cancelling active work before closing...")
    return False
```

- [ ] **Step 4: Wire close handling into `MainWindow`**

In `src/pitchstems/app.py`, import the helper:

```python
from pitchstems import gui_shutdown
```

Add state in `MainWindow.__init__` after worker job setup:

```python
self.close_after_worker = False
```

Update `closeEvent`:

```python
        def closeEvent(self, event) -> None:
            if not gui_shutdown.request_window_close(self):
                event.ignore()
                return
            self.save_editor_state()
            super().closeEvent(event)
```

In `gui_processing.flush_messages`, after successful active `ENABLE_PROCESS` handling, add:

```python
                if getattr(window, "close_after_worker", False):
                    window.close_after_worker = False
                    window.close()
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_shutdown.py tests/test_gui_jobs.py tests/test_gui_processing.py -q
```

Expected: shutdown, job, and processing tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/gui_shutdown.py src/pitchstems/app.py src/pitchstems/gui_processing.py tests/test_gui_shutdown.py
git commit -m "fix: defer GUI close while cancelling active work"
```

---

### Task 4: Communicate Native ML Cancellation Boundaries

**Files:**
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `src/pitchstems/pipeline.py`
- Modify: `README.md`
- Modify: `tests/test_pipeline_storage.py`

- [ ] **Step 1: Write failing log-boundary test**

Append this test to `tests/test_pipeline_storage.py`:

```python
def test_full_pipeline_logs_deferred_cancellation_boundary(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    messages: list[str] = []

    def fake_normalize(_input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return output_path

    def fake_separate(_audio_path, output_dir, **_kwargs):
        stem_path = output_dir / "source_bass.wav"
        stem_path.parent.mkdir(parents=True, exist_ok=True)
        stem_path.write_bytes(b"stem")
        return [StemResult("bass", stem_path)]

    monkeypatch.setattr(pipeline, "normalize_to_wav", fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", fake_separate)

    process_audio_file(
        input_path,
        tmp_path / "out",
        generate_midi=False,
        create_zip=False,
        log=messages.append,
        cancelled=lambda: False,
    )

    assert "Cancellation will take effect between native model stages." in messages
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_full_pipeline_logs_deferred_cancellation_boundary -q
```

Expected before implementation: FAIL because the boundary message is not logged.

- [ ] **Step 3: Add pipeline boundary logging**

In `process_audio_file`, after the existing audio-prep logs and only when a cancellation callback exists, add:

```python
            if cancelled is not None:
                log("Cancellation will take effect between native model stages.")
```

In `start_full_processing` and `start_midi_processing`, when `request_worker_cancel(window)` is later wired to a cancel button or close action, use activity text:

```python
window.set_activity_message("Cancelling after the current model stage...")
```

- [ ] **Step 4: Document the boundary**

In `README.md`, under Validation tiers or GUI workflow, add:

```markdown
Cancellation is cooperative. PitchStems checks for cancellation between orchestration
steps, but native BS-RoFormer and Basic Pitch calls may need to finish their current
model stage before the GUI can report the job as cancelled.
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py -q
```

Expected: all pipeline storage tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/pipeline.py src/pitchstems/gui_processing.py tests/test_pipeline_storage.py README.md
git commit -m "docs: clarify native cancellation boundaries"
```

---

### Task 5: Extract Shared Editor Music Models

**Files:**
- Create: `src/pitchstems/editor_models.py`
- Modify: `src/pitchstems/editor_project.py`
- Modify: `src/pitchstems/chord_analysis.py`
- Modify: `src/pitchstems/scale_analysis.py`
- Modify: `tests/test_editor_project.py`
- Modify: `tests/test_chord_analysis.py`

- [ ] **Step 1: Write compatibility tests**

Append this test to `tests/test_editor_project.py`:

```python
def test_editor_project_reexports_shared_music_models() -> None:
    from pitchstems.editor_models import ChordRegion as SharedChordRegion
    from pitchstems.editor_models import NoteEvent as SharedNoteEvent
    from pitchstems.editor_project import ChordRegion, NoteEvent

    assert ChordRegion is SharedChordRegion
    assert NoteEvent is SharedNoteEvent
```

Append this test to `tests/test_chord_analysis.py`:

```python
def test_detect_chords_returns_shared_chord_region_type() -> None:
    from pitchstems.editor_models import ChordRegion
    from pitchstems.editor_project import NoteEvent

    chords = detect_chords([
        NoteEvent("piano", 0.0, 1.0, 60, 90),
        NoteEvent("piano", 0.0, 1.0, 64, 90),
        NoteEvent("piano", 0.0, 1.0, 67, 90),
    ])

    assert chords
    assert isinstance(chords[0], ChordRegion)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor_project.py::test_editor_project_reexports_shared_music_models tests/test_chord_analysis.py::test_detect_chords_returns_shared_chord_region_type -q
```

Expected before implementation: FAIL because `pitchstems.editor_models` does not exist.

- [ ] **Step 3: Move neutral dataclasses**

Create `src/pitchstems/editor_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    stem: str
    start: float
    end: float
    pitch: int
    velocity: int

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class ChordRegion:
    start: float
    end: float
    label: str
    confidence: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)
```

In `src/pitchstems/editor_project.py`, import and re-export these names:

```python
from pitchstems.editor_models import ChordRegion, NoteEvent
```

Remove the duplicate local `NoteEvent` and `ChordRegion` dataclass definitions from `editor_project.py`.

- [ ] **Step 4: Remove runtime back-import from chord analysis**

In `src/pitchstems/chord_analysis.py`, replace the TYPE_CHECKING import and local runtime import with:

```python
from pitchstems.editor_models import ChordRegion, NoteEvent
```

In `src/pitchstems/scale_analysis.py`, import `ChordRegion` and `NoteEvent` from `pitchstems.editor_models` instead of `pitchstems.editor_project`.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor_project.py tests/test_chord_analysis.py tests/test_theory.py -q
```

Expected: editor project, chord analysis, and theory tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/editor_models.py src/pitchstems/editor_project.py src/pitchstems/chord_analysis.py src/pitchstems/scale_analysis.py tests/test_editor_project.py tests/test_chord_analysis.py
git commit -m "refactor: share editor music models"
```

---

### Task 6: Add Refactor Guardrails For MainWindow And TimelineView

**Files:**
- Modify: `docs/architecture/product-architecture.md`
- Modify: `docs/superpowers/plans/2026-06-07-remaining-audit-fixes.md`

- [ ] **Step 1: Add concrete split checkpoints**

In `docs/architecture/product-architecture.md`, extend the extraction-target bullets with these checkpoints:

```markdown
Before adding new editor UI behavior:

- `MainWindow` should lose direct ownership of harmony inspector actions by moving dialog creation and action enablement behind a `gui_harmony_dialogs.py` module.
- `TimelineView` should expose pure geometry/editing helpers for chord drag, selection, and visible-note windows so those behaviors can be tested without constructing a full `QGraphicsScene`.
- Chord analysis should split into at least `chord_models.py`, `chord_naming.py`, `chord_scoring.py`, and `chord_detection.py` once shared editor models are stable.
```

- [ ] **Step 2: Verify docs only**

Run:

```powershell
git diff --check main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/architecture/product-architecture.md docs/superpowers/plans/2026-06-07-remaining-audit-fixes.md
git commit -m "docs: plan remaining GUI and harmony extractions"
```

---

### Task 7: Final Verification And PR Update

**Files:**
- Review all touched files.

- [ ] **Step 1: Run targeted behavior checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py tests/test_gui_processing.py tests/test_gui_shutdown.py tests/test_pipeline_storage.py tests/test_editor_project.py tests/test_chord_analysis.py tests/test_theory.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run full project check**

Run:

```powershell
git diff --check main...HEAD
.\scripts\check.ps1 -GuiSmoke -Build
```

Expected: whitespace clean; Ruff clean; full tests pass; compileall passes; `pip check` passes; doctor, GUI smoke, and build pass.

- [ ] **Step 3: Push and check PR**

Run:

```powershell
git push
gh pr checks 6 --watch=false
```

Expected: branch pushes to `fix/audit-hardening`; PR #6 GitHub checks pass.
