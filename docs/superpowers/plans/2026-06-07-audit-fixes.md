# PitchStems Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the remaining audit findings with small, reviewable changes and verify with targeted regression tests, Git whitespace checks, and the full project check.

**Architecture:** Keep the current desktop-app structure intact while hardening validation scripts, making full pipeline cancellation atomic for newly created projects, and documenting the remaining larger refactor paths. Behavioral changes go through tests first; documentation-only risk items are handled with focused repo guidance.

**Tech Stack:** Python 3.10, pytest, Ruff, PowerShell, GitHub Actions, PySide6, Basic Pitch, ONNX Runtime GPU, BS-RoFormer.

---

### Task 1: Add Full-Pipeline Cancellation Cleanup

**Files:**
- Modify: `tests/test_pipeline_storage.py`
- Modify: `src/pitchstems/pipeline.py`

- [ ] **Step 1: Write the failing test**

Add a test that cancels after stem separation and asserts the newly created `.pitchstems` project directory is removed:

```python
def test_full_pipeline_cancellation_removes_partial_new_project(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    should_cancel = False

    def fake_normalize(_input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return output_path

    def fake_separate(_audio_path, output_dir, **_kwargs):
        nonlocal should_cancel
        stem_path = output_dir / "source_bass.wav"
        stem_path.parent.mkdir(parents=True, exist_ok=True)
        stem_path.write_bytes(b"stem")
        should_cancel = True
        return [StemResult("bass", stem_path)]

    monkeypatch.setattr(pipeline, "normalize_to_wav", fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", fake_separate)

    with pytest.raises(pipeline.PipelineCancelledError):
        process_audio_file(
            input_path,
            tmp_path / "out",
            generate_midi=False,
            create_zip=False,
            cancelled=lambda: should_cancel,
        )

    assert not list((tmp_path / "out").glob("*.pitchstems"))
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_full_pipeline_cancellation_removes_partial_new_project -q
```

Expected before implementation: FAIL because a partial project directory remains.

- [ ] **Step 3: Implement cleanup**

Wrap the body of `process_audio_file` after project directory creation in `try`/`except PipelineCancelledError`, and remove only the newly-created project directory when cancellation occurs. Add a helper that verifies the directory is inside `output_root`, has suffix `.pitchstems`, and is not a symlink before `shutil.rmtree`.

- [ ] **Step 4: Run the targeted test and existing pipeline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py -q
```

Expected after implementation: all pipeline storage tests pass.

---

### Task 2: Harden Whitespace Validation

**Files:**
- Modify: `scripts/check.ps1`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/pull_request_template.md`
- Modify: `src/pitchstems/chord_gap_analysis.py`
- Modify: `src/pitchstems/editor_project.py`

- [ ] **Step 1: Add Git whitespace checks to local validation**

In `scripts/check.ps1`, use `Invoke-Checked` to run `git diff --check` for the working tree, staged diff, and, when available, the branch diff against `origin/main` or `main`.

- [ ] **Step 2: Add Git whitespace checks to CI**

In `.github/workflows/ci.yml`, fetch full history and run:

```powershell
git diff --check origin/main...HEAD
```

- [ ] **Step 3: Update the PR checklist**

Add a checkbox for `git diff --check main...HEAD`.

- [ ] **Step 4: Remove the known EOF blank lines**

Trim the extra trailing blank lines from `src/pitchstems/chord_gap_analysis.py` and `src/pitchstems/editor_project.py`.

- [ ] **Step 5: Verify**

Run:

```powershell
git diff --check main...HEAD
```

Expected: no output and exit code 0.

---

### Task 3: Harden Windows GPU Setup Command Handling

**Files:**
- Modify: `scripts/setup-windows-gpu.ps1`

- [ ] **Step 1: Add checked native command execution**

Add the same `Invoke-Checked` helper style used in `scripts/check.ps1`, then wrap every `py`, `nvidia-smi`, `.venv\Scripts\python`, and `.venv\Scripts\pitchstems` command in the setup script.

- [ ] **Step 2: Verify syntax**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$null = [scriptblock]::Create((Get-Content -Raw .\scripts\setup-windows-gpu.ps1)); 'syntax ok'"
```

Expected: prints `syntax ok`.

---

### Task 4: Document Remaining Architecture and Validation Risk

**Files:**
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Create: `constraints/windows-gpu.txt`

- [ ] **Step 1: Add Windows GPU constraints**

Create `constraints/windows-gpu.txt` with the supported CUDA wheel pins:

```text
torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
onnxruntime>=1.23.2,<1.24
onnxruntime-gpu[cuda,cudnn]>=1.23.2,<1.24
```

- [ ] **Step 2: Point setup docs and script comments to constraints**

Update README and setup script comments so the pinned Windows GPU stack has one documented source of truth.

- [ ] **Step 3: Document refactor targets**

Add a short architecture note naming `MainWindow`, `gui_timeline.py`, and `chord_analysis.py` as deliberate future extraction targets, including the neutral shared model module direction for `ChordRegion` and `NoteEvent`.

- [ ] **Step 4: Strengthen real-audio smoke guidance**

Document the manual real-audio smoke command and expected artifacts so release validation is repeatable even when GPU CI is unavailable.

---

### Task 5: Final Verification

**Files:**
- Review all touched files.

- [ ] **Step 1: Run targeted checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py -q
git diff --check main...HEAD
```

- [ ] **Step 2: Run full project check**

Run:

```powershell
.\scripts\check.ps1 -GuiSmoke -Build
```

- [ ] **Step 3: Review diff**

Run:

```powershell
git diff --stat
git diff --check main...HEAD
```

Expected: focused diff, no whitespace errors, full project check passes.
