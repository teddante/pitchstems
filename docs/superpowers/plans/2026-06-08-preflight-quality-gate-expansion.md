# Preflight And Quality Gate Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deepen preflight diagnostics and expand strict gates over newly extracted stable modules without destabilizing the large PySide surface.

**Architecture:** Extend `PreflightReport` with checks that can run before project creation: output writability, native module presence, CUDA details, and model registry availability. Add only small stable modules to mypy and coverage after tests exist.

**Tech Stack:** Python 3.10, pytest, mypy, pytest-cov, GitHub Actions.

---

## File Structure

- Modify: `src/pitchstems/preflight.py` for optional output and model registry checks.
- Modify: `src/pitchstems/pipeline.py` to pass output root into preflight.
- Modify: `scripts/check.ps1` and `pyproject.toml` to include new stable modules after extraction.
- Test: `tests/test_preflight.py`, `tests/test_pipeline_storage.py`.
- Modify: `.github/workflows/ci.yml` only if local check command changes.

### Task 1: Add Output Directory Preflight

**Files:**
- Modify: `src/pitchstems/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from pitchstems.preflight import run_preflight


def test_preflight_reports_unwritable_output_root(monkeypatch, tmp_path: Path) -> None:
    def fake_write_text(self, text: str, encoding: str = "utf-8") -> int:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    report = run_preflight(require_ml=False, output_root=tmp_path)

    assert not report.ok
    assert "Output directory" in report.failure_summary()
```

- [ ] **Step 2: Run test to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py::test_preflight_reports_unwritable_output_root -q`
Expected: FAIL because `output_root` is not accepted.

- [ ] **Step 3: Implement output check**

Add `output_root: Path | None = None` to `run_preflight`. Add:

```python
def _output_directory_check(output_root: Path) -> PreflightCheck:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / ".pitchstems-preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return PreflightCheck("Output directory", True, f"writable: {output_root}")
    except Exception as exc:
        return PreflightCheck("Output directory", False, str(exc))
```

Call it from `run_preflight` when `output_root is not None`.

- [ ] **Step 4: Verify preflight tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py -q`
Expected: PASS.

### Task 2: Pass Output Root From Pipeline

**Files:**
- Modify: `src/pitchstems/pipeline.py`
- Test: `tests/test_pipeline_storage.py`

- [ ] **Step 1: Update preflight call**

In `process_audio_file`, change:

```python
report = run_preflight(
    require_ml=True,
    requested_device=separation_options.device if separation_options else None,
)
```

to:

```python
report = run_preflight(
    require_ml=True,
    requested_device=separation_options.device if separation_options else None,
    output_root=output_root,
)
```

- [ ] **Step 2: Verify pipeline tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py tests/test_preflight.py -q`
Expected: PASS.

### Task 3: Add Native Model Registry Preflight

**Files:**
- Modify: `src/pitchstems/preflight.py`
- Test: `tests/test_preflight.py`

- [ ] **Step 1: Write failing registry tests**

```python
from pitchstems.preflight import run_preflight


def test_preflight_can_skip_model_registry_check_when_ml_not_required() -> None:
    report = run_preflight(require_ml=False, model_key="bs_roformer_sw")

    assert report.ok
```

- [ ] **Step 2: Add optional registry check**

Add `model_key: str | None = None` to `run_preflight`. When `require_ml and model_key`, add:

```python
def _model_registry_check(model_key: str) -> PreflightCheck:
    try:
        from bs_roformer import MODEL_REGISTRY
        from pitchstems.model_catalog import model_choice

        choice = model_choice(model_key)
        if MODEL_REGISTRY.get(choice.native_model_id) is None:
            return PreflightCheck("BS-RoFormer model registry", False, choice.native_model_id)
        return PreflightCheck("BS-RoFormer model registry", True, choice.native_model_id)
    except Exception as exc:
        return PreflightCheck("BS-RoFormer model registry", False, str(exc))
```

- [ ] **Step 3: Pass model key from pipeline**

In `process_audio_file`, pass:

```python
model_key=separation_options.model_key if separation_options else None,
```

- [ ] **Step 4: Verify tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preflight.py tests/test_pipeline_storage.py -q`
Expected: PASS.

### Task 4: Expand Strict Gates To Extracted Stable Modules

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/check.ps1`

- [ ] **Step 1: Add mypy modules**

Add only modules that exist and have focused tests:

```toml
  "src/pitchstems/gui_editor_model.py",
  "src/pitchstems/gui_layout_policy.py",
  "src/pitchstems/gui_pipeline_model.py",
  "src/pitchstems/timeline_render_policy.py",
```

- [ ] **Step 2: Add coverage modules**

In `scripts/check.ps1`, add:

```powershell
        --cov=pitchstems.gui_editor_model `
        --cov=pitchstems.gui_layout_policy `
        --cov=pitchstems.gui_pipeline_model `
        --cov=pitchstems.timeline_render_policy `
```

- [ ] **Step 3: Verify full gate**

Run: `.\scripts\check.ps1 -GuiSmoke -Build`
Expected: PASS with total coverage at or above 90%.

### Task 5: Commit

```powershell
git add src/pitchstems/preflight.py src/pitchstems/pipeline.py pyproject.toml scripts/check.ps1 tests/test_preflight.py tests/test_pipeline_storage.py
git commit -m "test: deepen preflight and quality gates"
```

## Self-Review

- Spec coverage: covers shallow preflight and scoped quality gate expansion.
- Placeholder scan: model registry and output checks are fully defined.
- Type consistency: `run_preflight` gains `output_root` and `model_key` optional keyword parameters.
