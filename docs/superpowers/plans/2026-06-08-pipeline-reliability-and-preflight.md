# Pipeline Reliability And Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bad native backend output, missing dependencies, invalid devices, and failed full pipeline runs explicit and diagnosable.

**Architecture:** Add a small preflight/report layer consumed by CLI, GUI, and pipeline start paths. Keep native library calls thin, but validate before expensive work and fail clearly when expected artifacts are not produced.

**Tech Stack:** Python dataclasses, existing doctor checks, pytest monkeypatching.

---

## Files

- Create: `src/pitchstems/preflight.py`
- Modify: `src/pitchstems/pipeline.py`
- Modify: `src/pitchstems/separation.py`
- Modify: `src/pitchstems/doctor.py`
- Modify: `src/pitchstems/cli.py`
- Modify: `src/pitchstems/gui_processing.py`
- Test: `tests/test_separation_logging.py`
- Test: `tests/test_pipeline_storage.py`
- Test: `tests/test_doctor.py`

## Task 1: Fail Empty Separation Output

- [ ] **Step 1: Write failing test**

Add to `tests/test_separation_logging.py`:

```python
def test_separation_fails_when_native_backend_produces_no_stems(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"wav")

    monkeypatch.setattr(separation, "download_model", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(separation, "_registry_model", lambda *_args: SimpleNamespace(slug="", checkpoint="model.ckpt", config="model.yaml"))
    (tmp_path / "model.ckpt").write_text("weights", encoding="utf-8")
    (tmp_path / "model.yaml").write_text("config", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "bs_roformer", SimpleNamespace(MODEL_REGISTRY={}))
    monkeypatch.setitem(sys.modules, "bs_roformer.inference", SimpleNamespace(proc_folder=lambda _args: None))

    with pytest.raises(RuntimeError, match="did not produce any stems"):
        separation.separate_stems(audio, tmp_path / "out")
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_separation_logging.py::test_separation_fails_when_native_backend_produces_no_stems -q`

Expected: FAIL because `separate_stems()` returns an empty list.

- [ ] **Step 2: Raise explicit error**

In `src/pitchstems/separation.py`, after deduping produced stems:

```python
if not stems:
    raise RuntimeError(
        "BS-RoFormer did not produce any stems. Check the selected model, device, and native backend logs."
    )
```

If `options.selected_stem` filters all stems, raise:

```python
if options.selected_stem and not stems:
    raise RuntimeError(f"BS-RoFormer did not produce requested stem: {options.selected_stem}")
```

- [ ] **Step 3: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_separation_logging.py -q`

Expected: PASS.

## Task 2: Add Preflight Reports

- [ ] **Step 1: Write tests for preflight failure details**

Create `tests/test_preflight.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from pitchstems.preflight import run_preflight


def test_preflight_reports_missing_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("missing ffmpeg")))
    report = run_preflight(require_ml=False)
    assert not report.ok
    assert any(check.name == "FFmpeg" and not check.ok for check in report.checks)


def test_preflight_reports_cuda_request_without_cuda(monkeypatch) -> None:
    monkeypatch.setattr("pitchstems.preflight.require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr("pitchstems.preflight.torch_status", lambda: SimpleNamespace(installed=True, cuda_available=False, device_name=""))
    report = run_preflight(require_ml=False, requested_device="cuda")
    assert not report.ok
    assert any(check.name == "PyTorch CUDA" and not check.ok for check in report.checks)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py -q`

Expected: FAIL because `preflight.py` does not exist.

- [ ] **Step 2: Implement `preflight.py`**

Create `src/pitchstems/preflight.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from pitchstems.acceleration import onnxruntime_status, torch_status
from pitchstems.audio import require_ffmpeg


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def failure_summary(self) -> str:
        failures = [f"{check.name}: {check.detail}" for check in self.checks if not check.ok]
        return "; ".join(failures)


def run_preflight(require_ml: bool = True, requested_device: str | None = None) -> PreflightReport:
    checks: list[PreflightCheck] = []
    try:
        checks.append(PreflightCheck("FFmpeg", True, require_ffmpeg()))
    except Exception as exc:
        checks.append(PreflightCheck("FFmpeg", False, str(exc)))

    if requested_device == "cuda":
        status = torch_status()
        checks.append(
            PreflightCheck(
                "PyTorch CUDA",
                bool(status.installed and status.cuda_available),
                status.device_name if status.cuda_available else "CUDA is not available to PyTorch",
            )
        )

    if require_ml:
        ort = onnxruntime_status()
        checks.append(
            PreflightCheck(
                "ONNX Runtime",
                bool(ort.installed),
                ", ".join(ort.providers) if ort.installed else "ONNX Runtime is not installed",
            )
        )
    return PreflightReport(checks)
```

- [ ] **Step 3: Verify**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py -q`

Expected: PASS.

## Task 3: Use Preflight Before Long Jobs

- [ ] **Step 1: Write pipeline preflight test**

Add to `tests/test_pipeline_storage.py`:

```python
def test_full_pipeline_fails_before_project_creation_when_preflight_fails(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(
        pipeline,
        "run_preflight",
        lambda **_kwargs: SimpleNamespace(ok=False, failure_summary=lambda: "FFmpeg: missing"),
    )

    with pytest.raises(RuntimeError, match="Preflight failed: FFmpeg: missing"):
        pipeline.process_audio_file(source, tmp_path / "out")

    assert not list((tmp_path / "out").glob("*.pitchstems"))
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_full_pipeline_fails_before_project_creation_when_preflight_fails -q`

Expected: FAIL.

- [ ] **Step 2: Call preflight before creating project directories**

In `src/pitchstems/pipeline.py`, import `run_preflight` and call after input path validation:

```python
report = run_preflight(
    require_ml=True,
    requested_device=separation_options.device if separation_options else None,
)
if not report.ok:
    raise RuntimeError(f"Preflight failed: {report.failure_summary()}")
```

- [ ] **Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py tests/test_pipeline_storage.py::test_full_pipeline_fails_before_project_creation_when_preflight_fails -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 4: Make Failed Full-Run State Explicit

- [ ] **Step 1: Add behavior test**

Add to `tests/test_pipeline_storage.py`:

```python
def test_failed_full_pipeline_writes_failed_manifest(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(pipeline, "run_preflight", lambda **_kwargs: SimpleNamespace(ok=True))
    monkeypatch.setattr(pipeline, "normalize_to_wav", lambda input_path, output_path: output_path.write_bytes(b"wav") or output_path)
    monkeypatch.setattr(pipeline, "separate_stems", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("native failed")))

    with pytest.raises(RuntimeError, match="native failed"):
        pipeline.process_audio_file(source, tmp_path / "out")

    manifests = list((tmp_path / "out").glob("*.pitchstems/pitchstems.project.json"))
    assert manifests
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "native failed" in manifest["last_error"]
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_failed_full_pipeline_writes_failed_manifest -q`

Expected: FAIL.

- [ ] **Step 2: Add failed manifest writer**

In `src/pitchstems/project_store.py`, add:

```python
def save_failed_project_manifest(project_dir: Path, source_audio: Path | None, normalized_audio: Path | None, error: str) -> Path:
    manifest_path = project_manifest_path(project_dir)
    manifest = {
        "format": "pitchstems-project",
        "format_version": PROJECT_FORMAT_VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "name": project_dir.name.removesuffix(".pitchstems"),
        "status": "failed",
        "last_error": error,
        "source_audio": _relative_or_absolute(project_dir, source_audio),
        "normalized_audio": _relative_or_absolute(project_dir, normalized_audio),
        "stems": [],
        "midi_files": [],
        "combined_midi": None,
        "zip_path": None,
        "settings": {},
        "editor": {},
    }
    _write_json_atomic(manifest_path, manifest)
    return manifest_path
```

In `process_audio_file()`, catch non-cancelled exceptions after project dir creation:

```python
except Exception as exc:
    save_failed_project_manifest(project_dir, locals().get("project_source_audio"), locals().get("normalized_audio"), str(exc))
    raise
```

Keep `PipelineCancelledError` cleanup behavior unchanged.

- [ ] **Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py tests/test_project_store.py -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 5: Commit Pipeline Reliability Work

- [ ] **Step 1: Review diff**

Run: `git diff -- src tests`

Expected: only preflight, pipeline reliability, and tests changed.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src\pitchstems\preflight.py src\pitchstems\pipeline.py src\pitchstems\separation.py src\pitchstems\project_store.py src\pitchstems\doctor.py src\pitchstems\cli.py src\pitchstems\gui_processing.py tests\test_preflight.py tests\test_separation_logging.py tests\test_pipeline_storage.py tests\test_doctor.py
git commit -m "fix: add pipeline preflight and failure state"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers empty separation, preflight diagnostics, device checks, and failed full-run state.
- Placeholder scan: each task includes exact test and implementation shape.
- Type consistency: `PreflightCheck`, `PreflightReport`, and `run_preflight()` are introduced once and reused.
