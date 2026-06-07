# PitchStems Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the repository audit findings while keeping the current PySide app usable and verifying each change with targeted tests plus the full project check.

**Architecture:** Land the high-confidence dependency and validation fixes first, then introduce explicit job/cancellation primitives, then reduce coupling in the GUI and music-analysis modules through compatibility-preserving extracts. Keep the current package layout and PySide workflow intact while aligning each step with the documented future sidecar/job architecture.

**Tech Stack:** Python 3.10, PySide6, pytest, Ruff, PowerShell setup/check scripts, hatchling packaging, Basic Pitch, ONNX Runtime GPU, BS-RoFormer.

---

## Workstreams

1. Dependency metadata and reproducibility: make `pip check` pass in the Windows GPU environment and make that check part of the normal safety net.
2. Long-running job lifecycle: add explicit cancellation state and cooperative cancellation checks where the Python orchestration can act.
3. GUI state boundaries: group `MainWindow` runtime state into focused dataclasses without changing user-visible behavior.
4. Chord/editor module boundaries: extract chord analysis from editor project loading while preserving existing imports.
5. Theory module boundaries: split theory scale analysis and gap analysis once chord extraction is stable.
6. CI and docs: make validation expectations visible in CI, README, CONTRIBUTING, and the setup script.

## Branch Strategy

- Create a short-lived branch: `fix/audit-hardening`.
- Commit after each task when checks for that task pass.
- Keep each commit reviewable; do not combine dependency fixes with large refactors.
- Open a draft PR after Task 3 if the branch is getting large, then continue with follow-up PRs for Task 4 and Task 5.

---

### Task 1: Make Dependency Metadata Verifiable

**Files:**
- Modify: `scripts/setup-windows-gpu.ps1`
- Modify: `scripts/check.ps1`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Create the branch**

Run:

```powershell
git switch -c fix/audit-hardening
```

Expected: branch switches to `fix/audit-hardening`.

- [ ] **Step 2: Reproduce the current metadata failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Expected before the fix: failure mentioning `basic-pitch` requires `onnxruntime`.

- [ ] **Step 3: Update the GPU setup script to preserve `onnxruntime` metadata**

In `scripts/setup-windows-gpu.ps1`, replace the ONNX Runtime install block with:

```powershell
Write-Host "Replacing default CPU ML wheels with Windows CUDA wheels..."
.\.venv\Scripts\python -m pip uninstall -y torch torchvision onnxruntime onnxruntime-gpu
.\.venv\Scripts\python -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128

# Basic Pitch declares a dependency on the `onnxruntime` distribution. Keep that
# metadata installed, then install `onnxruntime-gpu` last so the importable
# runtime exposes CUDA providers.
.\.venv\Scripts\python -m pip install "onnxruntime>=1.23.2,<1.24"
.\.venv\Scripts\python -m pip install "onnxruntime-gpu[cuda,cudnn]>=1.23.2,<1.24"

Write-Host "Checking installed package metadata..."
.\.venv\Scripts\python -m pip check
```

- [ ] **Step 4: Add `pip check` to the project check script**

In `scripts/check.ps1`, after the compile step, add:

```powershell
Write-Host "Checking installed package metadata..."
& $python @pythonArgs -m pip check
```

Expected: local full checks now catch broken installed dependency metadata.

- [ ] **Step 5: Add `pip check` to CI**

In `.github/workflows/ci.yml`, after the compile step and before GUI smoke, add:

```yaml
      - name: Check installed package metadata
        run: python -m pip check
```

Expected: CI catches resolver and metadata breakage in the dev/gui install.

- [ ] **Step 6: Document the GPU metadata behavior**

Add a short note to README under Windows NVIDIA GPU install:

```markdown
The GPU setup keeps both `onnxruntime` package metadata and `onnxruntime-gpu`
installed. Basic Pitch declares `onnxruntime`, while PitchStems imports ONNX
Runtime from the GPU wheel so CUDA providers remain available. `pip check` is
part of the project check and should pass after setup.
```

Add the same validation command to CONTRIBUTING checks:

```markdown
The project check also runs `python -m pip check` so broken installed
dependency metadata is caught before review.
```

- [ ] **Step 7: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\check.ps1 -GuiSmoke -Build
```

Expected: both commands pass; doctor still reports ONNX Runtime CUDA providers in the GPU environment.

- [ ] **Step 8: Commit**

Run:

```powershell
git add scripts/setup-windows-gpu.ps1 scripts/check.ps1 .github/workflows/ci.yml README.md CONTRIBUTING.md
git commit -m "fix: verify installed dependency metadata"
```

---

### Task 2: Add Cooperative Pipeline Cancellation

**Files:**
- Modify: `src/pitchstems/pipeline.py`
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `tests/test_pipeline_storage.py`
- Create: `tests/test_gui_processing.py`

- [ ] **Step 1: Add a pipeline cancellation exception and callback type**

In `src/pitchstems/pipeline.py`, add near the imports and dataclasses:

```python
from collections.abc import Callable as CallableABC


CancelCheck = CallableABC[[], bool]


class PipelineCancelledError(RuntimeError):
    """Raised when a user-requested cancellation stops pipeline orchestration."""
```

- [ ] **Step 2: Add a helper that raises on cancellation**

In `src/pitchstems/pipeline.py`, add:

```python
def _raise_if_cancelled(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise PipelineCancelledError("Processing cancelled.")
```

- [ ] **Step 3: Thread cancellation through pipeline entry points**

Add `cancelled: CancelCheck | None = None` to `process_audio_file(...)` and `process_midi_from_stems(...)`.

Call `_raise_if_cancelled(cancelled)`:
- after source audio copy
- after WAV normalization
- after stem separation
- before each stem transcription in `process_midi_from_stems`
- after each stem transcription
- before `_replace_midi_outputs(...)`

Pass the callback from `process_audio_file(...)` into `process_midi_from_stems(...)`.

- [ ] **Step 4: Write targeted cancellation tests**

Add to `tests/test_pipeline_storage.py`:

```python
def test_process_midi_from_stems_cancellation_preserves_existing_outputs(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stem_path = project_dir / "stems" / "song_bass.wav"
    old_midi = project_dir / "midi" / "bass" / "old.mid"
    old_export = project_dir / "export" / "bass.mid"
    for path in [stem_path, old_midi, old_export]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    def fake_transcribe(stem_name, _audio_path, output_dir, **_kwargs):
        midi_path = output_dir / f"{stem_name}.mid"
        _write_midi(midi_path, 40)
        return MidiResult(stem_name, midi_path)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", fake_transcribe)

    with pytest.raises(pipeline.PipelineCancelledError):
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[StemResult("bass", stem_path)],
            midi_stems={"bass"},
            create_zip=False,
            cancelled=lambda: True,
        )

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"
```

- [ ] **Step 5: Wire cancellation into GUI worker requests**

In `src/pitchstems/gui_processing.py`, add `cancelled: Callable[[], bool]` to `FullRunRequest` and `MidiRunRequest`, then pass it to `process_audio_file(...)` and `process_midi_from_stems(...)`.

When building requests, use:

```python
cancelled=lambda token=window.worker_token: not window.is_active_worker_token(token)
```

Create the token before building the request so the callback captures the correct token.

- [ ] **Step 6: Treat cancellation as a normal worker outcome**

In `run_full_pipeline(...)` and `run_midi_stage(...)`, add a specific handler before the broad `except Exception`:

```python
    except PipelineCancelledError:
        window.logger.info("Processing cancelled")
        window.messages.put(("WORKER_LOG", token, "Processing cancelled."))
```

Import `PipelineCancelledError` from `pitchstems.pipeline`.

- [ ] **Step 7: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_pipeline_storage.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_gui_processing.py -q
.\scripts\check.ps1
```

Expected: all targeted tests pass and full check passes.

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/pitchstems/pipeline.py src/pitchstems/gui_processing.py tests/test_pipeline_storage.py tests/test_gui_processing.py
git commit -m "fix: add cooperative pipeline cancellation"
```

---

### Task 3: Make GUI Job State Explicit

**Files:**
- Create: `src/pitchstems/gui_jobs.py`
- Modify: `src/pitchstems/app.py`
- Modify: `src/pitchstems/gui_processing.py`
- Modify: `src/pitchstems/gui_editor_load.py`
- Modify: `src/pitchstems/gui_transport_flow.py`
- Create: `tests/test_gui_jobs.py`

- [ ] **Step 1: Add job state primitives**

Create `src/pitchstems/gui_jobs.py`:

```python
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkerJobState:
    next_token: int = 0
    active_token: int | None = None

    def start(self) -> int:
        self.next_token += 1
        self.active_token = self.next_token
        return self.next_token

    def cancel(self) -> bool:
        had_active = self.active_token is not None
        self.next_token += 1
        self.active_token = None
        return had_active

    def is_active(self, token: int) -> bool:
        return self.active_token == token


@dataclass
class EditorLoadJobState:
    token: int = 0
    activity_tokens: set[int] = field(default_factory=set)
    worker: threading.Thread | None = None

    def next(self) -> int:
        self.token += 1
        return self.token


@dataclass
class MidiPreviewJobState:
    token: int = 0
    workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = field(default_factory=dict)

    def next(self) -> int:
        self.token += 1
        self.workers.clear()
        return self.token
```

- [ ] **Step 2: Test job state**

Create `tests/test_gui_jobs.py`:

```python
from pitchstems.gui_jobs import EditorLoadJobState, MidiPreviewJobState, WorkerJobState


def test_worker_job_state_starts_cancels_and_rejects_stale_tokens() -> None:
    state = WorkerJobState()
    first = state.start()
    assert state.is_active(first)

    assert state.cancel()
    assert not state.is_active(first)

    second = state.start()
    assert second != first
    assert state.is_active(second)


def test_editor_load_job_state_tracks_activity_tokens() -> None:
    state = EditorLoadJobState()
    token = state.next()
    state.activity_tokens.add(token)
    assert token in state.activity_tokens


def test_midi_preview_job_state_next_clears_workers(tmp_path) -> None:
    state = MidiPreviewJobState()
    state.workers[(tmp_path, "bass")] = (state.token, None)  # type: ignore[arg-type]
    state.next()
    assert state.workers == {}
```

- [ ] **Step 3: Replace scattered fields in `MainWindow`**

In `src/pitchstems/app.py`, replace:

```python
self.worker_token = 0
self.active_worker_token: int | None = None
self.editor_load_worker: threading.Thread | None = None
self.editor_load_token = 0
self.editor_load_activity_tokens: set[int] = set()
self.midi_preview_token = 0
self.midi_preview_workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = {}
```

with:

```python
self.worker_jobs = WorkerJobState()
self.editor_load_jobs = EditorLoadJobState()
self.midi_preview_jobs = MidiPreviewJobState()
```

Import the three dataclasses from `pitchstems.gui_jobs`.

- [ ] **Step 4: Preserve compatibility through methods**

Update methods in `app.py`:

```python
def start_worker_token(self) -> int:
    return gui_processing.start_worker_token(self)

def is_active_worker_token(self, token: int) -> bool:
    return self.worker_jobs.is_active(token)
```

Then update helper modules to use `window.worker_jobs`, `window.editor_load_jobs`, and `window.midi_preview_jobs` instead of direct token fields.

- [ ] **Step 5: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_gui_jobs.py tests\test_gui_smoke.py tests\test_gui_transport.py -q
.\scripts\check.ps1 -GuiSmoke
```

Expected: targeted GUI tests and GUI smoke pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/pitchstems/gui_jobs.py src/pitchstems/app.py src/pitchstems/gui_processing.py src/pitchstems/gui_editor_load.py src/pitchstems/gui_transport_flow.py tests/test_gui_jobs.py
git commit -m "refactor: make gui job state explicit"
```

---

### Task 4: Extract Chord Analysis From Editor Project Loading

**Files:**
- Create: `src/pitchstems/chord_analysis.py`
- Modify: `src/pitchstems/editor_project.py`
- Modify: `tests/test_editor_project.py`
- Create: `tests/test_chord_analysis.py`

- [ ] **Step 1: Create the new module as a compatibility extraction**

Move these items from `editor_project.py` into `chord_analysis.py` without changing behavior:
- `ChordScoringOptions`
- `ChordAnalysis`
- `PartialChordCandidate`
- `detect_chords`
- `active_notes_at`
- `midi_velocity_energy`
- `analyze_chord_at`
- `analyze_chord_region`
- `analyze_chord`
- `identify_chord`
- chord candidate/scoring/helper functions used only by those functions

Keep `NoteEvent` and `ChordRegion` in `editor_project.py` during this task to minimize blast radius.

- [ ] **Step 2: Re-export compatibility symbols**

At the bottom of the imports in `editor_project.py`, import the extracted public symbols:

```python
from pitchstems.chord_analysis import (
    ChordAnalysis,
    ChordScoringOptions,
    PartialChordCandidate,
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    analyze_chord_region,
    detect_chords,
    identify_chord,
    midi_velocity_energy,
)
```

Existing callers and tests that import from `pitchstems.editor_project` must keep working.

- [ ] **Step 3: Move direct chord tests**

Move tests that only exercise chord naming/scoring from `tests/test_editor_project.py` into `tests/test_chord_analysis.py`. Keep MIDI reading and editor-project construction tests in `tests/test_editor_project.py`.

The imports in the new test file should use:

```python
from pitchstems.chord_analysis import analyze_chord, analyze_chord_at, analyze_chord_region
from pitchstems.editor_project import NoteEvent
```

- [ ] **Step 4: Verify no behavior changed**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_editor_project.py tests\test_chord_analysis.py tests\test_harmony_inspector.py -q
.\scripts\check.ps1
```

Expected: all tests pass without changed assertions.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/pitchstems/chord_analysis.py src/pitchstems/editor_project.py tests/test_editor_project.py tests/test_chord_analysis.py
git commit -m "refactor: extract chord analysis module"
```

---

### Task 5: Split Theory Analysis After Chord Extraction

**Files:**
- Create: `src/pitchstems/scale_analysis.py`
- Create: `src/pitchstems/chord_gap_analysis.py`
- Modify: `src/pitchstems/theory.py`
- Modify: `tests/test_theory.py`

- [ ] **Step 1: Extract scale and key analysis**

Move scale registry, scale candidates, tonal-center scoring, roman numeral helpers, and theory report helpers into `scale_analysis.py`.

Keep public imports available from `theory.py`:

```python
from pitchstems.scale_analysis import (
    ScaleCandidate,
    ScaleDefinition,
    TheoryAnalysis,
    analyze_theory_at,
    analyze_theory_region,
    fit_clamp,
    spelling_preference_from_scale_label,
    theory_analysis_report,
)
```

- [ ] **Step 2: Extract chord-gap suggestion logic**

Move `ChordGapSuggestion`, `ChordGapAnalysis`, `analyze_chord_gap`, `chord_gap_report`, and gap helper functions into `chord_gap_analysis.py`.

Keep public imports available from `theory.py`:

```python
from pitchstems.chord_gap_analysis import (
    ChordGapAnalysis,
    ChordGapSuggestion,
    analyze_chord_gap,
    chord_gap_report,
)
```

- [ ] **Step 3: Keep `theory.py` as a compatibility facade**

After extraction, `theory.py` should contain imports/re-exports only, plus constants that are part of the public surface if any remain. Do not change call sites in GUI modules in this task.

- [ ] **Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_theory.py tests\test_harmony_inspector.py tests\test_editor_project.py -q
.\scripts\check.ps1
```

Expected: all tests pass without changed theory behavior.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/pitchstems/scale_analysis.py src/pitchstems/chord_gap_analysis.py src/pitchstems/theory.py tests/test_theory.py
git commit -m "refactor: split theory analysis modules"
```

---

### Task 6: Reduce MainWindow Pass-Through Coupling

**Files:**
- Modify: `src/pitchstems/app.py`
- Modify: `src/pitchstems/gui_project_flow.py`
- Modify: `src/pitchstems/gui_editor_state.py`
- Modify: `src/pitchstems/gui_transport_flow.py`
- Modify: existing GUI tests as needed

- [ ] **Step 1: Identify pass-through methods with no local logic**

Run:

```powershell
rg "def .*\\(self.*\\):\\n\\s+gui_" src\pitchstems\app.py -n
```

Expected: list of methods that simply delegate to helper modules.

- [ ] **Step 2: Remove pass-throughs only where Qt signal wiring does not require bound methods**

For direct internal calls, replace `window.method_name(...)` with `module.function_name(window, ...)`. Keep bound methods that are connected directly to Qt signals unless replacing them improves clarity.

Example replacement:

```python
# Before
window.refresh_playback_mix()

# After
gui_transport_flow.refresh_playback_mix(window)
```

- [ ] **Step 3: Preserve user-facing behavior**

Do not rename buttons, menu actions, settings keys, manifest fields, or log messages in this task.

- [ ] **Step 4: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_gui_smoke.py tests\test_gui_transport.py tests\test_gui_timeline.py tests\test_editor_state.py -q
.\scripts\check.ps1 -GuiSmoke
```

Expected: GUI behavior tests and smoke pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/pitchstems/app.py src/pitchstems/gui_project_flow.py src/pitchstems/gui_editor_state.py src/pitchstems/gui_transport_flow.py tests
git commit -m "refactor: reduce main window delegation surface"
```

---

### Task 7: Tighten Runtime Validation And Documentation

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `.github/pull_request_template.md`
- Modify: `docs/architecture/product-architecture.md`

- [ ] **Step 1: Add validation tiers to README**

Document:

```markdown
Validation tiers:

- Fast source check: `.\scripts\check.ps1`
- GUI/package check: `.\scripts\check.ps1 -GuiSmoke -Build`
- GPU/runtime check after setup or ML dependency changes: `.\scripts\check.ps1 -Gpu`
- Manual real-audio smoke when changing separation/transcription behavior:
  run a short local audio file, reopen the `.pitchstems` project, and confirm stems,
  MIDI, combined MIDI, manifest, editor timeline, and optional ZIP are present.
```

- [ ] **Step 2: Update PR template**

Add:

```markdown
- [ ] `python -m pip check` passes in the touched environment
- [ ] Real-audio smoke completed when separation/transcription behavior changed
```

- [ ] **Step 3: Update architecture docs with near-term migration boundary**

In `docs/architecture/product-architecture.md`, add a short note that the PySide phase now has:
- explicit job identity/cancellation state
- compatibility facades for extracted music-analysis modules
- a path to sidecar job messages without changing current project manifests

- [ ] **Step 4: Verify docs and full checks**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
git diff --check
```

Expected: full check passes and no whitespace errors.

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md CONTRIBUTING.md .github/pull_request_template.md docs/architecture/product-architecture.md
git commit -m "docs: document audit validation tiers"
```

---

## Final Verification

Run after all tasks on the branch:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\scripts\check.ps1 -GuiSmoke -Build
git status --short --branch
git log --oneline --decorate -n 8
```

Expected:
- `pip check` exits 0.
- Full check with GUI smoke and build exits 0.
- Git status shows only intentional branch state.
- Recent commits are small and reviewable.

If the branch is ready for GitHub:

```powershell
git push -u origin fix/audit-hardening
gh pr create --draft --title "Fix audit hardening findings" --body-file .github/pull_request_template.md
```

Before marking the repo-level goal complete, confirm all audit findings are either fixed in code or explicitly tracked as a scoped follow-up with a reason.

## Self-Review

- Spec coverage: all six audit findings are covered by Tasks 1 through 7.
- Placeholder scan: no intentionally blank tasks remain.
- Type consistency: new job-state classes use token names that map to existing GUI worker token concepts.
- Scope check: this can be executed as one branch, but Tasks 4 through 6 are good candidates for follow-up PRs if review size grows.
