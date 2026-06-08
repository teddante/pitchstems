# Audit Follow-Up Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the eight follow-up issues found in the repo-wide audit after the audit-hardening branch landed.

**Architecture:** Keep the app local-first and preserve existing `.pitchstems` compatibility. Separate user-visible correctness fixes from infrastructure and architecture-debt fixes so each commit is reviewable and verifiable. Favor TDD for behavioral bugs, then use docs/gate updates for explicitly bounded quality debt.

**Tech Stack:** Python 3.10, PySide6, pytest, mypy, pytest-cov, PowerShell, GitHub Actions, pip-audit.

---

## Files

- Modify: `src/pitchstems/pipeline.py`
- Modify: `src/pitchstems/project_store.py`
- Modify: `src/pitchstems/gui_widgets.py`
- Modify: `src/pitchstems/gui_project_flow.py`
- Modify: `src/pitchstems/preflight.py`
- Modify: `src/pitchstems/editor_project.py`
- Modify: `src/pitchstems/chord_scoring.py`
- Modify: `src/pitchstems/chord_detection.py`
- Modify: `src/pitchstems/chord_explanation.py`
- Modify: `.github/workflows/ml-dependencies.yml`
- Modify: `constraints/windows-gpu.txt`
- Modify: `scripts/setup-windows-gpu.ps1`
- Create: `docs/architecture/quality-gate-roadmap.md`
- Modify: `README.md`
- Test: `tests/test_pipeline_storage.py`
- Test: `tests/test_project_store.py`
- Test: `tests/test_gui_widgets.py`
- Test: `tests/test_gui_project_flow.py`
- Test: `tests/test_preflight.py`
- Test: `tests/test_editor_project.py`

## Task 1: Preserve Successful Manifest When ZIP Packaging Fails

**Files:**
- Modify: `tests/test_pipeline_storage.py`
- Modify: `src/pitchstems/pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline_storage.py`:

```python
def test_full_pipeline_zip_failure_preserves_success_manifest(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    def fake_normalize(_input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return output_path

    def fake_separate(_audio_path, stems_dir, **_kwargs):
        stem_path = stems_dir / "song_bass.wav"
        stem_path.parent.mkdir(parents=True, exist_ok=True)
        stem_path.write_bytes(b"stem")
        return [StemResult("bass", stem_path)]

    monkeypatch.setattr(pipeline, "normalize_to_wav", fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", fake_separate)
    monkeypatch.setattr(
        pipeline,
        "_zip_project_outputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("zip failed")),
    )

    with pytest.raises(RuntimeError, match="zip failed"):
        pipeline.process_audio_file(source, tmp_path / "out", generate_midi=False, create_zip=True)

    manifests = list((tmp_path / "out").glob("*.pitchstems/pitchstems.project.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest.get("status") != "failed"
    assert manifest["stems"] == [{"name": "bass", "path": "stems/song_bass.wav", "stem_id": "bass"}]
    assert manifest["midi_files"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_full_pipeline_zip_failure_preserves_success_manifest -q
```

Expected: FAIL because the manifest is overwritten with `status: failed` and empty `stems`.

- [ ] **Step 3: Track whether the successful manifest was written**

In `src/pitchstems/pipeline.py`, add a flag before the `try` block in `process_audio_file()`:

```python
    project_manifest_written = False
```

After `save_project_manifest(...)` succeeds, set:

```python
        project_manifest_written = True
```

Update the broad exception handler:

```python
    except Exception as exc:
        if not project_manifest_written:
            save_failed_project_manifest(project_dir, project_source_audio, normalized_audio, str(exc))
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_full_pipeline_zip_failure_preserves_success_manifest -q
```

Expected: PASS.

## Task 2: Clear Stale Audio Path On Invalid Drag/Drop

**Files:**
- Modify: `tests/test_gui_widgets.py`
- Create: `tests/test_gui_project_flow.py`
- Modify: `src/pitchstems/gui_widgets.py`
- Modify: `src/pitchstems/gui_project_flow.py`

- [ ] **Step 1: Write the failing widget test**

Add to `tests/test_gui_widgets.py`:

```python
class _Url:
    def __init__(self, path: Path) -> None:
        self.path = path

    def isLocalFile(self) -> bool:
        return True

    def toLocalFile(self) -> str:
        return str(self.path)


class _MimeData:
    def __init__(self, path: Path) -> None:
        self.path = path

    def urls(self):
        return [_Url(self.path)]


class _DropEvent:
    def __init__(self, path: Path) -> None:
        self.path = path

    def mimeData(self):
        return _MimeData(self.path)


def test_drop_zone_invalid_drop_clears_previous_audio_path(tmp_path: Path) -> None:
    _app()
    widget = DropZone()
    valid = tmp_path / "song.wav"
    invalid = tmp_path / "notes.txt"
    valid.write_bytes(b"RIFF")
    invalid.write_text("not audio", encoding="utf-8")
    widget.set_audio_file(valid)

    widget.dropEvent(_DropEvent(invalid))

    assert widget.path is None
    assert "Unsupported audio file type" in widget.text()
```

- [ ] **Step 2: Write the failing dialog-selection test**

Create `tests/test_gui_project_flow.py`:

```python
from pathlib import Path

from pitchstems.gui_project_flow import set_audio_path


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, _timeout: int) -> None:
        self.messages.append(message)


class _DropZone:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.reset_count = 0

    def set_audio_file(self, path: Path) -> None:
        self.path = path

    def reset_prompt(self) -> None:
        self.path = None
        self.reset_count += 1


class _Window:
    def __init__(self, previous_path: Path) -> None:
        self.drop_zone = _DropZone(previous_path)
        self.logs: list[str] = []
        self.status = _StatusBar()
        self.reset_paths: list[Path] = []

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def statusBar(self) -> _StatusBar:
        return self.status

    def reset_stage_state(self, path: Path) -> None:
        self.reset_paths.append(path)


def test_set_audio_path_invalid_selection_clears_previous_audio_path(tmp_path: Path) -> None:
    previous = tmp_path / "previous.wav"
    invalid = tmp_path / "notes.txt"
    previous.write_bytes(b"RIFF")
    invalid.write_text("not audio", encoding="utf-8")
    window = _Window(previous)

    set_audio_path(window, invalid)

    assert window.drop_zone.path is None
    assert window.drop_zone.reset_count == 1
    assert window.reset_paths == []
    assert any("Unsupported audio file type" in message for message in window.logs)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_widgets.py::test_drop_zone_invalid_drop_clears_previous_audio_path -q
.\.venv\Scripts\python.exe -m pytest tests/test_gui_project_flow.py::test_set_audio_path_invalid_selection_clears_previous_audio_path -q
```

Expected: both FAIL because the stale path remains active after invalid input.

- [ ] **Step 4: Clear path before showing invalid-input errors**

In `src/pitchstems/gui_widgets.py`, update `dropEvent()`:

```python
        if error:
            self.path = None
            self.setText(error)
            self.setToolTip(error)
            if self.on_path_changed:
                self.on_path_changed(None)
            return
```

In `src/pitchstems/gui_project_flow.py`, update the invalid branch in `set_audio_path()`:

```python
    if error:
        window.drop_zone.reset_prompt()
        window.append_log(error)
        window.statusBar().showMessage(error, 5000)
        return
```

- [ ] **Step 5: Run GUI path tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gui_widgets.py tests/test_gui_project_flow.py tests/test_gui_processing.py -q
```

Expected: PASS.

## Task 3: Surface Failed Project Manifests On Load

**Files:**
- Modify: `tests/test_project_store.py`
- Modify: `src/pitchstems/project_store.py`

- [ ] **Step 1: Write failing failed-manifest load test**

Add to `tests/test_project_store.py`:

```python
def test_load_pipeline_result_rejects_failed_manifest_with_last_error(tmp_path: Path) -> None:
    from pitchstems.project_store import save_failed_project_manifest

    project_dir = tmp_path / "song.pitchstems"
    source = project_dir / "audio" / "song.wav"
    normalized = project_dir / "work" / "song.wav"
    source.parent.mkdir(parents=True)
    normalized.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    normalized.write_bytes(b"wav")
    save_failed_project_manifest(project_dir, source, normalized, "native failed")

    with pytest.raises(ValueError, match="Project processing failed: native failed"):
        load_pipeline_result(project_dir)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py::test_load_pipeline_result_rejects_failed_manifest_with_last_error -q
```

Expected: FAIL because `load_pipeline_result()` returns an empty `PipelineResult`.

- [ ] **Step 3: Reject failed manifests in `load_pipeline_result()`**

In `src/pitchstems/project_store.py`, after `_validate_manifest(...)` in `load_pipeline_result()` add:

```python
    if manifest.get("status") == "failed":
        last_error = manifest.get("last_error")
        detail = f": {last_error}" if isinstance(last_error, str) and last_error else ""
        raise ValueError(f"Project processing failed{detail}")
```

- [ ] **Step 4: Verify project-store behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py -q
```

Expected: PASS.

## Task 4: Cache Editor Query Indexes

**Files:**
- Modify: `tests/test_editor_project.py`
- Modify: `src/pitchstems/editor_project.py`

- [ ] **Step 1: Write failing cache test**

Add to `tests/test_editor_project.py`:

```python
def test_editor_project_reuses_query_indexes(tmp_path: Path, monkeypatch) -> None:
    import pitchstems.editor_project as editor_project_module

    note = NoteEvent("piano", 0.0, 1.0, 60, 90)
    project = EditorProject(
        project_dir=tmp_path,
        source_audio=tmp_path / "song.wav",
        tracks=[EditorTrack("piano", tmp_path / "piano.wav")],
        notes=[note],
        chords=[ChordRegion(0.0, 1.0, "C", 0.8)],
        duration=1.0,
    )
    note_index_calls = 0
    chord_index_calls = 0

    class CountingNoteIndex:
        def __init__(self, notes):
            nonlocal note_index_calls
            note_index_calls += 1
            self.notes = notes

    class CountingChordIndex:
        def __init__(self, chords, duration):
            nonlocal chord_index_calls
            chord_index_calls += 1
            self.chords = chords
            self.duration = duration

    monkeypatch.setattr(editor_project_module, "NoteIndex", CountingNoteIndex)
    monkeypatch.setattr(editor_project_module, "ChordIndex", CountingChordIndex)

    assert project.note_index is project.note_index
    assert project.chord_index is project.chord_index
    assert note_index_calls == 1
    assert chord_index_calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor_project.py::test_editor_project_reuses_query_indexes -q
```

Expected: FAIL because each property access constructs a new index.

- [ ] **Step 3: Use `cached_property`**

In `src/pitchstems/editor_project.py`, import:

```python
from functools import cached_property
```

Replace the two `@property` decorators:

```python
    @cached_property
    def note_index(self) -> NoteIndex:
        return NoteIndex(self.notes)

    @cached_property
    def chord_index(self) -> ChordIndex:
        return ChordIndex(self.chords, self.duration)
```

- [ ] **Step 4: Verify editor query behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor_query.py tests/test_editor_project.py tests/test_harmony_inspector.py -q
```

Expected: PASS.

## Task 5: Strengthen Preflight Native ML Checks

**Files:**
- Modify: `tests/test_preflight.py`
- Modify: `src/pitchstems/preflight.py`

- [ ] **Step 1: Write failing native-package preflight test**

Add to `tests/test_preflight.py`:

```python
def test_preflight_reports_missing_native_ml_packages(monkeypatch) -> None:
    import importlib.util

    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        "pitchstems.preflight.onnxruntime_status",
        lambda: SimpleNamespace(installed=True, providers=["CPUExecutionProvider"]),
    )

    def fake_find_spec(module_name: str):
        if module_name == "basic_pitch":
            return None
        if module_name == "bs_roformer":
            return object()
        return importlib.util.find_spec(module_name)

    monkeypatch.setattr("pitchstems.preflight.importlib.util.find_spec", fake_find_spec)

    report = run_preflight(require_ml=True)

    assert not report.ok
    assert any(check.name == "Basic Pitch" and not check.ok for check in report.checks)
    assert any(check.name == "BS-RoFormer native backend" and check.ok for check in report.checks)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py::test_preflight_reports_missing_native_ml_packages -q
```

Expected: FAIL because preflight does not check `basic_pitch` or `bs_roformer`.

- [ ] **Step 3: Add module checks to preflight**

In `src/pitchstems/preflight.py`, import:

```python
import importlib.util
```

Add helper:

```python
def _module_check(name: str, module_name: str) -> PreflightCheck:
    found = importlib.util.find_spec(module_name) is not None
    return PreflightCheck(name, found, "installed" if found else f"`{module_name}` missing")
```

Inside `if require_ml:`, append:

```python
        checks.append(_module_check("Basic Pitch", "basic_pitch"))
        checks.append(_module_check("BS-RoFormer native backend", "bs_roformer"))
```

- [ ] **Step 4: Verify preflight and pipeline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py tests/test_pipeline_storage.py::test_full_pipeline_fails_before_project_creation_when_preflight_fails -q
```

Expected: PASS.

## Task 6: Make GPU CI Prove CUDA Wheel Resolution

**Files:**
- Modify: `.github/workflows/ml-dependencies.yml`
- Modify: `scripts/setup-windows-gpu.ps1`
- Modify: `constraints/windows-gpu.txt`

- [ ] **Step 1: Pin GPU constraints to the CUDA runtime contract**

Update `constraints/windows-gpu.txt`:

```text
# Windows NVIDIA GPU runtime pins used by scripts/setup-windows-gpu.ps1 and CI GPU resolve proof.
torch==2.11.0
torchvision==0.26.0
onnxruntime>=1.23.2,<1.24
onnxruntime-gpu[cuda,cudnn]>=1.23.2,<1.24
```

Keep the PyTorch versions without `+cu128` because the CUDA wheel index supplies the local-version wheel.

- [ ] **Step 2: Make workflow follow setup script's CUDA wheel path**

In `.github/workflows/ml-dependencies.yml`, replace the GPU install step body with:

```yaml
          python -m pip install -U pip
          python -m pip install -c constraints/windows-gpu.txt -e ".[win-gpu]"
          python -m pip uninstall -y torch torchvision
          python -m pip install -c constraints/windows-gpu.txt torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Add a step after install:

```yaml
      - name: Verify CUDA PyTorch wheel was selected
        run: |
          python - <<'PY'
          import torch
          assert "+cu" in torch.__version__, torch.__version__
          print(torch.__version__)
          PY
```

- [ ] **Step 3: Keep setup script aligned**

Ensure `scripts/setup-windows-gpu.ps1` still installs PyTorch with:

```powershell
& .\.venv\Scripts\python -m pip install -c $gpuConstraints torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

- [ ] **Step 4: Verify workflow YAML parses**

Run:

```powershell
@'
from pathlib import Path
import yaml
for path in Path(".github/workflows").glob("*.yml"):
    yaml.safe_load(path.read_text())
print("workflow yaml ok")
'@ | .\.venv\Scripts\python.exe -
```

Expected: prints `workflow yaml ok`.

## Task 7: Remove Misleading Music-Analysis Facade Debt

**Files:**
- Modify: `src/pitchstems/chord_scoring.py`
- Modify: `src/pitchstems/chord_detection.py`
- Modify: `src/pitchstems/chord_explanation.py`
- Modify: `docs/architecture/product-architecture.md`

- [ ] **Step 1: Document current ownership honestly in module docstrings**

Add this module docstring at the top of `src/pitchstems/chord_scoring.py`:

```python
"""Compatibility exports for chord scoring internals.

The implementation still lives in ``pitchstems.chord_analysis`` so public imports
can stabilize before a larger mechanical extraction. Do not add new scoring logic
here; move the implementation from ``chord_analysis`` first.
"""
```

Add equivalent docstrings to `chord_detection.py` and `chord_explanation.py`, replacing `scoring` with `detection` and `explanation`.

- [ ] **Step 2: Update architecture debt note**

In `docs/architecture/product-architecture.md`, replace any statement implying `chord_scoring.py` owns scoring implementation with:

```markdown
| Chord scoring | `src/pitchstems/chord_scoring.py` | compatibility export surface; implementation still lives in `chord_analysis.py` pending mechanical extraction | existing chord analysis tests plus scoring fixture tests |
```

- [ ] **Step 3: Verify docs and imports**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chord_analysis.py tests/test_editor_project.py tests/test_theory.py -q
rg -n "compatibility export surface|implementation still lives" src/pitchstems/chord_scoring.py src/pitchstems/chord_detection.py src/pitchstems/chord_explanation.py docs/architecture/product-architecture.md
```

Expected: tests pass and `rg` finds the explicit architecture-debt language.

## Task 8: Document Remaining Type/Coverage Gate Gaps

**Files:**
- Create: `docs/architecture/quality-gate-roadmap.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Create quality gate roadmap**

Create `docs/architecture/quality-gate-roadmap.md`:

```markdown
# Quality Gate Roadmap

PitchStems currently runs Ruff, mypy on a scoped set of hardened modules,
pytest with focused coverage gates, compileall, pip check, doctor, GUI smoke,
and package build in `scripts/check.ps1`.

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
```

- [ ] **Step 2: Link roadmap from docs**

Add to `README.md` under Validation tiers:

```markdown
See `docs/architecture/quality-gate-roadmap.md` for the current typed/coverage surface and known gaps.
```

Add the same sentence to `CONTRIBUTING.md` under Checks.

- [ ] **Step 3: Verify evidence**

Run:

```powershell
rg -n "Quality Gate Roadmap|Known Gaps|typed/coverage surface" README.md CONTRIBUTING.md docs/architecture/quality-gate-roadmap.md
```

Expected: roadmap and links are found.

## Task 9: Final Verification And Commit

**Files:**
- All files modified above.

- [ ] **Step 1: Run targeted suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py tests/test_project_store.py tests/test_gui_widgets.py tests/test_gui_project_flow.py tests/test_preflight.py tests/test_editor_project.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full local gate**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
```

Expected: PASS.

- [ ] **Step 3: Run security and workflow checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip_audit
@'
from pathlib import Path
import yaml
for path in Path(".github/workflows").glob("*.yml"):
    yaml.safe_load(path.read_text())
print("workflow yaml ok")
'@ | .\.venv\Scripts\python.exe -
```

Expected: `pip_audit` reports no known vulnerabilities or a triaged report, and workflow YAML parses.

- [ ] **Step 4: Run contract evidence search**

Run:

```powershell
rg -n "zip failed|status.*failed|last_error|cached_property|CUDA PyTorch wheel|Basic Pitch|BS-RoFormer native backend|compatibility export surface|Quality Gate Roadmap" src tests docs .github README.md CONTRIBUTING.md constraints scripts
```

Expected: finds the fixed surfaces.

- [ ] **Step 5: Commit and push**

Run:

```powershell
git add src tests docs README.md CONTRIBUTING.md .github constraints scripts
git commit -m "fix: address audit follow-up hardening issues"
git push
```

Expected: commit and push succeed.

## Self-Review

- Spec coverage: all eight findings from the repo-wide audit are represented by Tasks 1-8, with Task 9 verifying the whole repair set.
- Vagueness scan: every task names concrete files, checks, and expected outcomes.
- Type consistency: planned function names and file names match the current codebase (`save_failed_project_manifest`, `validate_audio_input`, `NoteIndex`, `ChordIndex`, `run_preflight`).
