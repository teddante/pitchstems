# UI Layout And Visual Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Pipeline and Editor tabs easier to scan at common desktop widths and add repeatable visual/geometry checks.

**Architecture:** Add explicit layout policy helpers and screenshot smoke modes before changing widget layout. Keep all current controls available, but move dense settings behind existing tabs or collapsible sections where possible.

**Tech Stack:** Python 3.10, PySide6 offscreen rendering, pytest, local PNG artifacts ignored by git.

---

## File Structure

- Create: `src/pitchstems/gui_layout_policy.py` for stable width and density decisions.
- Modify: `src/pitchstems/app.py` to call the visual audit helper during smoke when requested.
- Modify: `src/pitchstems/gui_pipeline_page.py` to reduce first-screen text density.
- Modify: `src/pitchstems/gui_editor_page.py` to make side panels scrollable and width-aware.
- Modify: `src/pitchstems/gui_smoke.py` to capture optional visual audit screenshots.
- Modify: `.gitignore` to ignore `.codex-ui-audit/` if not already ignored.
- Test: `tests/test_gui_layout_policy.py`, existing GUI smoke.

### Task 1: Add Layout Policy Tests

**Files:**
- Create: `tests/test_gui_layout_policy.py`
- Create: `src/pitchstems/gui_layout_policy.py`

- [ ] **Step 1: Write failing tests**

```python
from pitchstems.gui_layout_policy import EditorLayoutPolicy, PipelineLayoutPolicy


def test_editor_layout_policy_uses_compact_panels_below_desktop_width() -> None:
    policy = EditorLayoutPolicy(window_width=900)

    assert policy.compact is True
    assert policy.harmony_panel_min_width == 260
    assert policy.track_panel_min_width == 240


def test_editor_layout_policy_uses_roomier_panels_on_default_window() -> None:
    policy = EditorLayoutPolicy(window_width=1220)

    assert policy.compact is False
    assert policy.harmony_panel_min_width == 300
    assert policy.track_panel_min_width == 280


def test_pipeline_layout_policy_keeps_intro_copy_short() -> None:
    policy = PipelineLayoutPolicy()

    assert len(policy.pipeline_intro) <= 110
    assert "BS-RoFormer" in policy.pipeline_intro
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_layout_policy.py -q`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement policy module**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditorLayoutPolicy:
    window_width: int

    @property
    def compact(self) -> bool:
        return self.window_width < 1040

    @property
    def harmony_panel_min_width(self) -> int:
        return 260 if self.compact else 300

    @property
    def track_panel_min_width(self) -> int:
        return 240 if self.compact else 280


@dataclass(frozen=True)
class PipelineLayoutPolicy:
    pipeline_intro: str = (
        "Drop audio, choose output settings, then run the local BS-RoFormer and Basic Pitch pipeline."
    )
```

- [ ] **Step 4: Verify tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_gui_layout_policy.py -q`
Expected: PASS.

### Task 2: Reduce Pipeline First-Screen Text Density

**Files:**
- Modify: `src/pitchstems/gui_pipeline_page.py`
- Test: `tests/test_gui_layout_policy.py`, GUI smoke

- [ ] **Step 1: Use the policy intro**

At the top of `gui_pipeline_page.py`, import:

```python
from pitchstems.gui_layout_policy import PipelineLayoutPolicy
```

Replace the long `intro = QLabel(...)` body with:

```python
intro = QLabel(PipelineLayoutPolicy().pipeline_intro)
```

- [ ] **Step 2: Verify startup smoke**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
$env:PITCHSTEMS_GUI_SMOKE="startup"
.\.venv\Scripts\python.exe -c "from pitchstems.app import main; raise SystemExit(main())"
```

Expected: exit code 0.

### Task 3: Make Editor Panels Width-Aware

**Files:**
- Modify: `src/pitchstems/gui_editor_page.py`
- Test: GUI smoke

- [ ] **Step 1: Apply policy widths**

Import:

```python
from pitchstems.gui_layout_policy import EditorLayoutPolicy
```

In `build_editor_page`, create:

```python
policy = EditorLayoutPolicy(window_width=window.width())
```

Replace fixed side panel widths:

```python
editor_side_panel.setMinimumWidth(policy.harmony_panel_min_width)
track_mix_panel.setMinimumWidth(policy.track_panel_min_width)
```

- [ ] **Step 2: Verify project smoke**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
$env:PITCHSTEMS_GUI_SMOKE="project"
.\.venv\Scripts\python.exe -c "from pitchstems.app import main; raise SystemExit(main())"
```

Expected: exit code 0.

### Task 4: Add Visual Audit Screenshot Mode

**Files:**
- Modify: `src/pitchstems/app.py`
- Modify: `src/pitchstems/gui_smoke.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add ignored artifact folder**

Add to `.gitignore`:

```gitignore
.codex-ui-audit/
```

- [ ] **Step 2: Add screenshot helper**

Add to `gui_smoke.py`:

```python
def capture_visual_audit(window, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    captures: list[Path] = []
    tab_names = [window.main_tabs.tabText(index) for index in range(window.main_tabs.count())]
    for width, height in [(1220, 780), (900, 700)]:
        window.resize(width, height)
        for tab_name in ["Pipeline", "Editor"]:
            window.main_tabs.setCurrentIndex(tab_names.index(tab_name))
            QApplication.processEvents()
            path = output_dir / f"{tab_name.lower()}-{width}x{height}.png"
            window.grab().save(str(path))
            captures.append(path)
    return captures
```

- [ ] **Step 3: Wire smoke-time capture**

In `app.py`, update the smoke import:

```python
from pitchstems.gui_smoke import capture_visual_audit, run_project_smoke, run_startup_smoke
```

Inside `run_smoke_and_exit`, after `run_project_smoke(window)` can run, add:

```python
visual_audit_dir = os.environ.get("PITCHSTEMS_VISUAL_AUDIT_DIR")
if visual_audit_dir:
    capture_visual_audit(window, Path(visual_audit_dir))
```

- [ ] **Step 4: Verify screenshots can be generated**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
$env:PITCHSTEMS_GUI_SMOKE="project"
$env:PITCHSTEMS_VISUAL_AUDIT_DIR=".codex-ui-audit"
.\.venv\Scripts\python.exe -c "from pitchstems.app import main; raise SystemExit(main())"
Get-ChildItem .codex-ui-audit
```

Expected: project smoke exits 0 and the folder contains `pipeline-1220x780.png`, `editor-1220x780.png`, `pipeline-900x700.png`, and `editor-900x700.png`. Do not commit generated PNG files.

### Task 5: Full Verification

- [ ] **Step 1: Run local GUI/package gate**

Run: `.\scripts\check.ps1 -GuiSmoke -Build`
Expected: PASS.

- [ ] **Step 2: Commit**

```powershell
git add .gitignore src/pitchstems/app.py src/pitchstems/gui_layout_policy.py src/pitchstems/gui_pipeline_page.py src/pitchstems/gui_editor_page.py src/pitchstems/gui_smoke.py tests/test_gui_layout_policy.py
git commit -m "ui: add layout policy and visual audit hooks"
```

## Self-Review

- Spec coverage: covers dense Pipeline first screen, width-hungry Editor layout, and repeatable visual checks.
- Placeholder scan: no unspecified screenshots are required; generated PNGs remain untracked.
- Type consistency: `EditorLayoutPolicy` and `PipelineLayoutPolicy` are introduced before use.
