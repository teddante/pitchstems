# Project Health Gates And Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make project health checks stronger and dependency resolution more reproducible without making local iteration painfully slow.

**Architecture:** Add constraints for dev/gui/cpu installs, broaden mypy/coverage to recently hardened modules, add a GPU dependency resolve workflow that does not require hardware, and add a scheduled Python dependency audit.

**Tech Stack:** PowerShell, pip constraints, pytest-cov, mypy, GitHub Actions, pip-audit.

---

## Files

- Create: `constraints/windows-dev.txt`
- Create: `constraints/windows-cpu.txt`
- Modify: `constraints/windows-gpu.txt`
- Modify: `scripts/check.ps1`
- Modify: `scripts/setup-windows-gpu.ps1`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/ml-dependencies.yml`
- Create: `.github/workflows/dependency-audit.yml`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`

## Task 1: Add Reproducible Constraints

- [ ] **Step 1: Generate constraints from known-good local environment**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable > constraints\windows-dev.txt
```

Expected: `constraints/windows-dev.txt` contains pinned versions for the current known-good dev/gui/ml environment.

- [ ] **Step 2: Add CPU constraints file**

Create `constraints/windows-cpu.txt` by copying `constraints/windows-dev.txt` and removing local-only editable lines if any exist. Keep `basic-pitch`, `bs-roformer-infer`, `onnxruntime`, `mido`, `PySide6`, `pytest`, `ruff`, and `mypy` pinned.

- [ ] **Step 3: Validate constrained install command**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints\windows-dev.txt -e ".[dev,gui]"
.\.venv\Scripts\python.exe -m pip check
```

Expected: PASS.

## Task 2: Broaden Mypy And Coverage In Layers

- [ ] **Step 1: Add hardened modules to mypy**

In `pyproject.toml`, extend `[tool.mypy].files`:

```toml
files = [
  "src/pitchstems/editor_models.py",
  "src/pitchstems/gui_jobs.py",
  "src/pitchstems/input_validation.py",
  "src/pitchstems/preflight.py",
  "src/pitchstems/project_store.py",
  "src/pitchstems/recent_projects.py",
  "src/pitchstems/time_format.py",
]
```

After the core safety and preflight plans are implemented, add `pipeline.py`, `separation.py`, and `transcription.py` if mypy passes without broad annotation churn.

- [ ] **Step 2: Add coverage modules**

In `scripts/check.ps1`, extend pytest coverage arguments:

```powershell
--cov=pitchstems.input_validation `
--cov=pitchstems.preflight `
--cov=pitchstems.pipeline `
```

Keep `--cov-fail-under=90` until added modules have enough tests, then raise only when the evidence supports it.

- [ ] **Step 3: Verify local check**

Run: `.\scripts\check.ps1`

Expected: PASS.

## Task 3: Add GPU Dependency Resolve Proof

- [ ] **Step 1: Update ML dependency workflow**

In `.github/workflows/ml-dependencies.yml`, add a job:

```yaml
  gpu-extra-resolves:
    name: GPU ML extra resolves
    runs-on: windows-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.10"
          cache: pip

      - name: Install GPU constraints without hardware check
        run: |
          python -m pip install -U pip
          python -m pip install -c constraints/windows-gpu.txt -e ".[win-gpu]"

      - name: Check installed metadata
        run: python -m pip check
```

- [ ] **Step 2: Verify workflow syntax**

Run:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
import yaml
for path in Path(".github/workflows").glob("*.yml"):
    yaml.safe_load(path.read_text())
print("workflow yaml ok")
PY
```

If PyYAML is not installed, run: `.\.venv\Scripts\python.exe -m pip install PyYAML` in the dev environment or use GitHub CI as the syntax validator.

Expected: workflow YAML parses.

## Task 4: Add Dependency Security Audit

- [ ] **Step 1: Add dev dependency**

In `pyproject.toml`, add to `dev`:

```toml
"pip-audit>=2.9",
```

- [ ] **Step 2: Add scheduled workflow**

Create `.github/workflows/dependency-audit.yml`:

```yaml
name: Dependency Audit

on:
  pull_request:
    branches: [main]
    paths:
      - "pyproject.toml"
      - "constraints/**"
      - ".github/workflows/dependency-audit.yml"
  workflow_dispatch:
  schedule:
    - cron: "41 6 * * 2"

permissions:
  contents: read

jobs:
  pip-audit:
    name: Python dependency audit
    runs-on: windows-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.10"
          cache: pip

      - name: Install audited environment
        run: |
          python -m pip install -U pip
          python -m pip install -c constraints/windows-cpu.txt -e ".[cpu,dev]"

      - name: Run pip-audit
        run: python -m pip_audit
```

- [ ] **Step 3: Verify locally**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install pip-audit
.\.venv\Scripts\python.exe -m pip_audit
```

Expected: PASS or a concrete vulnerability report that must be triaged before this plan is complete.

## Task 5: Document Constraints And Quality Gates

- [ ] **Step 1: Update README validation tiers**

In `README.md`, add:

```markdown
For reproducible Windows installs, use the constraints files in `constraints/` with the matching extra. Refresh constraints only after `.\scripts\check.ps1 -GuiSmoke -Build` and `python -m pip check` pass.
```

- [ ] **Step 2: Update CONTRIBUTING**

In `CONTRIBUTING.md`, add:

```markdown
When adding a module to mypy or coverage gates, keep the change small: add focused tests first, add the module to the gate, then run `.\scripts\check.ps1`. Do not lower coverage thresholds to make unrelated work pass.
```

- [ ] **Step 3: Verify docs mention gates**

Run: `rg -n "constraints|pip-audit|mypy|coverage" README.md CONTRIBUTING.md .github constraints`

Expected: relevant docs and workflows are found.

## Task 6: Commit Project Health Work

- [ ] **Step 1: Run full check**

Run: `.\scripts\check.ps1 -GuiSmoke -Build`

Expected: PASS.

- [ ] **Step 2: Commit**

Run:

```powershell
git add constraints\windows-dev.txt constraints\windows-cpu.txt constraints\windows-gpu.txt scripts\check.ps1 scripts\setup-windows-gpu.ps1 pyproject.toml .github\workflows\ci.yml .github\workflows\ml-dependencies.yml .github\workflows\dependency-audit.yml README.md CONTRIBUTING.md
git commit -m "ci: strengthen dependency and quality gates"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers scoped type/coverage expansion, reproducibility, GPU resolve proof, and security audit automation.
- Placeholder scan: exact files, commands, and workflow bodies are present.
- Type consistency: constraints files are named `windows-dev`, `windows-cpu`, and `windows-gpu`.
