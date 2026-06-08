# GUI Job Lifecycle And Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users a visible Cancel control and make full, MIDI, editor-load, and MIDI-preview worker lifecycles safe during reset and shutdown.

**Architecture:** Reuse the existing token-based stale-message filtering, but add a visible command path and lifecycle state for auxiliary workers. Avoid killing native library calls inside the PySide process; cancellation remains cooperative between model stages.

**Tech Stack:** PySide6, threading, queue, pytest with lightweight window doubles.

---

## Files

- Modify: `src/pitchstems/app.py`
- Modify: `src/pitchstems/gui_pipeline_page.py`
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `src/pitchstems/gui_shutdown.py`
- Modify: `src/pitchstems/gui_jobs.py`
- Modify: `src/pitchstems/gui_editor_load.py`
- Modify: `src/pitchstems/gui_transport_flow.py`
- Test: `tests/test_gui_processing.py`
- Test: `tests/test_gui_shutdown.py`
- Test: `tests/test_gui_jobs.py`

## Task 1: Add Visible Cancel Command

- [ ] **Step 1: Write failing tests**

Add to `tests/test_gui_processing.py`:

```python
def test_cancel_processing_requests_active_worker_and_updates_activity() -> None:
    window = DummyWindow()
    token = window.worker_jobs.start()

    assert gui_processing.cancel_processing(window) is True
    assert window.worker_jobs.is_cancel_requested(token)
    assert window.activities[-1] == "Cancelling after the current model stage..."
    assert "Cancellation requested." in window.logs[-1]


def test_cancel_processing_reports_no_active_worker() -> None:
    window = DummyWindow()

    assert gui_processing.cancel_processing(window) is False
    assert "No active processing job to cancel." in window.logs[-1]
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py::test_cancel_processing_requests_active_worker_and_updates_activity tests/test_gui_processing.py::test_cancel_processing_reports_no_active_worker -q`

Expected: FAIL because `cancel_processing()` does not exist.

- [ ] **Step 2: Implement cancel function**

In `src/pitchstems/gui_processing.py`:

```python
from pitchstems.gui_shutdown import CANCELLING_AFTER_STAGE_MESSAGE


def cancel_processing(window) -> bool:
    if not window.worker_jobs.cancel():
        window.append_log("No active processing job to cancel.")
        return False
    window.set_activity_message(CANCELLING_AFTER_STAGE_MESSAGE)
    window.append_log("Cancellation requested.")
    return True
```

- [ ] **Step 3: Wire button and menu action**

In `src/pitchstems/gui_pipeline_page.py`, create a `cancel_button` beside run buttons:

```python
window.cancel_button = QPushButton("Cancel")
window.cancel_button.setEnabled(False)
window.cancel_button.clicked.connect(window.cancel_processing)
```

In `src/pitchstems/app.py`, add:

```python
def cancel_processing(self) -> None:
    gui_processing.cancel_processing(self)
```

Update `set_processing_state()` to enable Cancel only while processing:

```python
self.cancel_button.setEnabled(is_processing)
```

- [ ] **Step 4: Verify cancel tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py tests/test_gui_shutdown.py -q`

Expected: PASS.

## Task 2: Add Auxiliary Worker Lifecycle State

- [ ] **Step 1: Write failing state tests**

Add to `tests/test_gui_jobs.py`:

```python
def test_editor_load_state_invalidates_and_marks_closing() -> None:
    state = EditorLoadJobState()
    first = state.next()
    state.worker = object()

    state.begin_closing()

    assert state.closing
    assert state.token > first
    assert state.worker is None


def test_midi_preview_state_invalidates_project_workers() -> None:
    state = MidiPreviewJobState()
    state.token = 4
    state.workers[(Path("song.pitchstems"), "vocals")] = (4, object())

    state.invalidate_all()

    assert state.token == 5
    assert state.workers == {}
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py::test_editor_load_state_invalidates_and_marks_closing tests/test_gui_jobs.py::test_midi_preview_state_invalidates_project_workers -q`

Expected: FAIL.

- [ ] **Step 2: Implement lifecycle methods**

In `src/pitchstems/gui_jobs.py`:

```python
@dataclass
class EditorLoadJobState:
    token: int = 0
    activity_tokens: set[int] = field(default_factory=set)
    worker: threading.Thread | None = None
    closing: bool = False

    def next(self) -> int:
        self.token += 1
        return self.token

    def begin_closing(self) -> None:
        self.token += 1
        self.activity_tokens.clear()
        self.worker = None
        self.closing = True


@dataclass
class MidiPreviewJobState:
    token: int = 0
    workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = field(default_factory=dict)
    closing: bool = False

    def invalidate_all(self) -> None:
        self.token += 1
        self.workers.clear()

    def begin_closing(self) -> None:
        self.invalidate_all()
        self.closing = True
```

- [ ] **Step 3: Verify state tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py -q`

Expected: PASS.

## Task 3: Apply Lifecycle State On Close And Project Reset

- [ ] **Step 1: Write close/reset tests**

Add to `tests/test_gui_shutdown.py`:

```python
def test_request_window_close_invalidates_auxiliary_workers_when_no_processing() -> None:
    window = DummyWindow()
    window.editor_load_jobs.worker = object()
    window.midi_preview_jobs.workers[(Path("song.pitchstems"), "vocals")] = (1, object())

    assert gui_shutdown.request_window_close(window) is True

    assert window.editor_load_jobs.closing
    assert window.midi_preview_jobs.closing
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_shutdown.py::test_request_window_close_invalidates_auxiliary_workers_when_no_processing -q`

Expected: FAIL.

- [ ] **Step 2: Invalidate auxiliaries in shutdown**

In `src/pitchstems/gui_shutdown.py`:

```python
def request_window_close(window) -> bool:
    if request_worker_cancel(window):
        window.close_after_worker = True
        window.set_activity_message(CANCELLING_AFTER_STAGE_MESSAGE)
        window.append_log("Close requested; cancelling active processing first.")
        return False
    window.editor_load_jobs.begin_closing()
    window.midi_preview_jobs.begin_closing()
    return True
```

When close is deferred until worker completion, call these same `begin_closing()` methods before `window.close()`.

- [ ] **Step 3: Guard auxiliary worker enqueue paths**

In `src/pitchstems/gui_editor_load.py`, before enqueueing success or failure:

```python
if window.editor_load_jobs.closing or token != window.editor_load_jobs.token:
    return
```

In `src/pitchstems/gui_transport_flow.py`, before enqueueing preview success or failure:

```python
if window.midi_preview_jobs.closing or token != window.midi_preview_jobs.token:
    return
```

- [ ] **Step 4: Verify GUI lifecycle tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_jobs.py tests/test_gui_shutdown.py tests/test_gui_processing.py -q
.\scripts\check.ps1 -GuiSmoke
```

Expected: PASS.

## Task 4: Commit GUI Lifecycle Work

- [ ] **Step 1: Review diff**

Run: `git diff -- src tests`

Expected: only GUI job lifecycle and tests changed.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src\pitchstems\app.py src\pitchstems\gui_pipeline_page.py src\pitchstems\gui_processing.py src\pitchstems\gui_shutdown.py src\pitchstems\gui_jobs.py src\pitchstems\gui_editor_load.py src\pitchstems\gui_transport_flow.py tests\test_gui_processing.py tests\test_gui_shutdown.py tests\test_gui_jobs.py
git commit -m "fix: expose cancellation and close auxiliary workers"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers visible cancellation, close behavior, editor-load workers, and MIDI-preview workers.
- Placeholder scan: all tests and implementation hooks are named.
- Type consistency: lifecycle flags live in `EditorLoadJobState` and `MidiPreviewJobState`.
