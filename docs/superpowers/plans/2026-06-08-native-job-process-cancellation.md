# Native Job Process Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a process-backed job boundary so native ML work can be hard-cancelled without corrupting existing project outputs.

**Architecture:** Add a small process runner next to the existing threaded GUI path, prove cancellation and result-message behavior with tests, then wire it behind an opt-in feature flag. Keep the current threaded path as the default until real-audio smoke proves parity.

**Tech Stack:** Python 3.10, multiprocessing, pathlib, queue messages, PySide6 GUI integration tests.

---

## File Structure

- Create: `src/pitchstems/native_jobs.py` for process lifecycle and messages.
- Modify: `src/pitchstems/gui_processing.py` to optionally use native process jobs.
- Modify: `docs/architecture/native-job-cancellation.md` to record the new boundary.
- Test: `tests/test_native_jobs.py`, `tests/test_gui_processing.py`, real-audio manual smoke.

### Task 1: Add Native Job Message Types

**Files:**
- Create: `src/pitchstems/native_jobs.py`
- Test: `tests/test_native_jobs.py`

- [ ] **Step 1: Write failing tests**

```python
from pitchstems.native_jobs import NativeJobMessage


def test_native_job_message_serializes_log_event() -> None:
    message = NativeJobMessage(kind="log", token=3, payload={"text": "started"})

    assert message.as_tuple() == ("NATIVE_JOB", "log", 3, {"text": "started"})
```

- [ ] **Step 2: Run test to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_jobs.py -q`
Expected: FAIL because `pitchstems.native_jobs` does not exist.

- [ ] **Step 3: Implement message dataclass**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NativeJobMessage:
    kind: str
    token: int
    payload: dict[str, Any]

    def as_tuple(self) -> tuple[str, str, int, dict[str, Any]]:
        return ("NATIVE_JOB", self.kind, self.token, self.payload)
```

- [ ] **Step 4: Verify test passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_jobs.py -q`
Expected: PASS.

### Task 2: Add Process Handle With Hard Cancel

**Files:**
- Modify: `src/pitchstems/native_jobs.py`
- Test: `tests/test_native_jobs.py`

- [ ] **Step 1: Write cancellation test**

```python
import time
from multiprocessing import Queue

from pitchstems.native_jobs import NativeJobProcess


def _sleeping_job(queue: Queue, token: int) -> None:
    queue.put(("started", token))
    time.sleep(30)


def test_native_job_process_can_be_terminated() -> None:
    job = NativeJobProcess.start(token=9, target=_sleeping_job)
    try:
        assert job.is_alive()
        job.cancel(timeout_seconds=2.0)
        assert not job.is_alive()
    finally:
        job.cancel(timeout_seconds=2.0)
```

- [ ] **Step 2: Implement process handle**

```python
from multiprocessing import Process, Queue
from typing import Callable


class NativeJobProcess:
    def __init__(self, token: int, process: Process, queue: Queue) -> None:
        self.token = token
        self.process = process
        self.queue = queue

    @classmethod
    def start(cls, token: int, target: Callable[[Queue, int], None]) -> "NativeJobProcess":
        queue: Queue = Queue()
        process = Process(target=target, args=(queue, token), daemon=True)
        process.start()
        return cls(token=token, process=process, queue=queue)

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def cancel(self, timeout_seconds: float = 5.0) -> None:
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout_seconds)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout_seconds)
```

- [ ] **Step 3: Verify cancellation**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_jobs.py -q`
Expected: PASS.

### Task 3: Add GUI Feature Flag

**Files:**
- Modify: `src/pitchstems/gui_processing.py`
- Test: `tests/test_gui_processing.py`

- [ ] **Step 1: Add feature flag helper**

Add:

```python
import os


def use_native_process_jobs() -> bool:
    return os.environ.get("PITCHSTEMS_NATIVE_PROCESS_JOBS") == "1"
```

- [ ] **Step 2: Add test**

```python
from pitchstems import gui_processing


def test_native_process_jobs_are_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("PITCHSTEMS_NATIVE_PROCESS_JOBS", raising=False)
    assert gui_processing.use_native_process_jobs() is False
    monkeypatch.setenv("PITCHSTEMS_NATIVE_PROCESS_JOBS", "1")
    assert gui_processing.use_native_process_jobs() is True
```

- [ ] **Step 3: Verify focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_processing.py tests/test_native_jobs.py -q`
Expected: PASS.

### Task 4: Document Process Boundary

**Files:**
- Modify: `docs/architecture/native-job-cancellation.md`

- [ ] **Step 1: Add current implementation note**

Add a section:

```markdown
## Process Job Boundary

`pitchstems.native_jobs.NativeJobProcess` provides the hard-cancel primitive for future native ML execution. The GUI keeps the existing threaded path by default, and process jobs are opt-in through `PITCHSTEMS_NATIVE_PROCESS_JOBS=1` until real-audio parity is proven.

The process boundary must preserve the current project safety rule: write into a staging project or staging output directory first, then promote outputs only after success. Cancellation may terminate the process and delete staging data, but it must not remove or mutate the last successful project manifest.
```

- [ ] **Step 2: Verify docs mention feature flag**

Run: `rg -n "NativeJobProcess|PITCHSTEMS_NATIVE_PROCESS_JOBS|staging" docs src tests`
Expected: matches in `native_jobs.py`, GUI processing tests, and architecture docs.

### Task 5: Full Verification And Commit

- [ ] **Step 1: Run local gate**

Run: `.\scripts\check.ps1 -GuiSmoke`
Expected: PASS.

- [ ] **Step 2: Commit**

```powershell
git add src/pitchstems/native_jobs.py src/pitchstems/gui_processing.py docs/architecture/native-job-cancellation.md tests/test_native_jobs.py tests/test_gui_processing.py
git commit -m "feat: add opt-in native process job boundary"
```

## Self-Review

- Spec coverage: covers the cooperative-only cancellation finding without forcing a risky immediate rewrite.
- Placeholder scan: the process class, feature flag, and documentation text are explicit.
- Type consistency: `NativeJobProcess` and `NativeJobMessage` are the new public contracts.
