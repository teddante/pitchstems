# UI Runtime Hardening Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current repo-wide audit findings by executing five focused plans with passing local gates and evidence for UI behavior, maintainability, performance, cancellation, preflight, and quality coverage.

**Architecture:** Keep the current PySide app working while extracting responsibilities behind tested seams. Treat the plans as reviewable slices: each one must leave `pitchstems-gui`, existing `.pitchstems` manifests, and CLI behavior intact.

**Tech Stack:** Python 3.10, PySide6, pytest, Ruff, mypy, pytest-cov, PowerShell validation, Windows GitHub Actions.

---

## Finding Map

| Audit finding | Owning plan | Completion evidence |
| --- | --- | --- |
| `MainWindow` is too centralized | `2026-06-08-main-window-controller-extraction.md` | New controller/view-state modules covered by tests and added to scoped mypy |
| Editor UI is dense and width-hungry | `2026-06-08-ui-layout-and-visual-regression.md` | Geometry tests plus offscreen screenshots for 1220x780 and 900x700 |
| Pipeline first screen is text-heavy | `2026-06-08-ui-layout-and-visual-regression.md` | Reduced first-screen density, advanced settings remain reachable |
| Timeline rendering is a performance hotspot | `2026-06-08-timeline-performance-hardening.md` | Dense MIDI benchmark/guard and redraw tests pass |
| Query indexes are helpful but partially linear | `2026-06-08-timeline-performance-hardening.md` | `NoteIndex` and `ChordIndex` tests cover bounded query behavior |
| Native cancellation is cooperative only | `2026-06-08-native-job-process-cancellation.md` | Process-backed job runner prototype with cancel test and unchanged threaded fallback path |
| Big UI files remain outside strict typing | `2026-06-08-preflight-quality-gate-expansion.md` | Newly extracted stable modules in mypy and coverage gates |
| Preflight is useful but shallow | `2026-06-08-preflight-quality-gate-expansion.md` | Preflight tests cover output writability, model registry/assets, and CUDA/runtime detail |

## Execution Order

1. [Main Window Controller Extraction](./2026-06-08-main-window-controller-extraction.md)
2. [UI Layout And Visual Regression](./2026-06-08-ui-layout-and-visual-regression.md)
3. [Timeline Performance Hardening](./2026-06-08-timeline-performance-hardening.md)
4. [Preflight And Quality Gate Expansion](./2026-06-08-preflight-quality-gate-expansion.md)
5. [Native Job Process Cancellation](./2026-06-08-native-job-process-cancellation.md)

## Campaign Gate

- [ ] `.\scripts\check.ps1 -GuiSmoke -Build` passes.
- [ ] `.\.venv\Scripts\python.exe -m pip_audit` reports no known vulnerabilities, with only expected local/CUDA wheel skips.
- [ ] `rg -n "PipelinePageModel|EditorLayoutPolicy|TimelineRenderPolicy|NativeJobProcess|PreflightReport" src tests docs` shows implemented runtime contracts and tests.
- [ ] Manual UI review confirms the Pipeline first screen and Editor tab are usable at 1220x780 and 900x700 without incoherent overlap.
- [ ] Existing `.pitchstems` project manifests open without migration errors.

## Self-Review

- Spec coverage: all eight audit findings are mapped to exactly one owning plan.
- Placeholder scan: no task depends on undefined future behavior; later process cancellation work is explicitly sequenced after smaller hardening.
- Type consistency: planned names are stable across plan files: `PipelinePageModel`, `EditorLayoutPolicy`, `TimelineRenderPolicy`, `NativeJobProcess`, and `PreflightReport`.
