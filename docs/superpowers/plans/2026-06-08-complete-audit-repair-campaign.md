# Complete Audit Repair Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every repo-wide audit finding through a sequenced set of reviewable implementation plans with explicit verification evidence.

**Architecture:** Treat the audit as a campaign, not a single patch. Each plan owns one subsystem boundary and leaves the app working after every commit. Existing PySide behavior and JSON `.pitchstems` compatibility stay intact while safer identifiers, job lifecycle, preflight checks, responsiveness, modular music analysis, and stronger quality gates are introduced.

**Tech Stack:** Python 3.10, PySide6, pytest, Ruff, mypy, PowerShell project checks, GitHub Actions.

---

## Campaign Scope

This campaign covers all high-priority findings from the June 8 repo audit:

- Stem/path safety and archive traversal risk.
- User-facing cancellation and background worker lifecycle.
- Empty/incomplete separation outputs and preflight diagnostics.
- GUI responsiveness during harmony analysis and early input validation.
- Chord/theory modularity plus interval-indexed query performance.
- Broader quality gates, reproducible dependency inputs, GPU resolve proof, and dependency security audit.

Out of scope for this campaign:

- Replacing PySide with Tauri/Svelte.
- Replacing JSON manifests with SQLite.
- Rewriting BS-RoFormer or Basic Pitch.
- Publishing releases, tags, or installers.

## Plan Set

Execute these plans in order:

1. [Core Stem And Path Safety](./2026-06-08-core-stem-and-path-safety.md)
2. [Pipeline Reliability And Preflight](./2026-06-08-pipeline-reliability-and-preflight.md)
3. [GUI Job Lifecycle And Cancellation](./2026-06-08-gui-job-lifecycle-and-cancellation.md)
4. [GUI Responsiveness And Input Validation](./2026-06-08-gui-responsiveness-and-input-validation.md)
5. [Music Analysis Modularity And Performance](./2026-06-08-music-analysis-modularity-and-performance.md)
6. [Project Health Gates And Reproducibility](./2026-06-08-project-health-gates-and-reproducibility.md)

## Completion Evidence

The campaign is complete only when all of this evidence exists:

- `.\scripts\check.ps1 -GuiSmoke -Build` passes locally.
- Targeted tests named in each plan pass.
- New or updated GitHub Actions workflows validate normal CI, ML CPU imports, dependency audit, and GPU dependency resolution without requiring GPU hardware.
- `rg -n "stem_id|safe_stem_key|Cancel|preflight|pip-audit|constraints/windows-dev|chord_scoring|NoteIndex" src tests docs .github` shows the planned runtime contracts and tests.
- Each plan has either been implemented in full or explicitly superseded by a later committed plan that covers the same acceptance criteria.

## Sequencing Notes

- Start with stem/path safety because later pipeline and archive work should consume safe identifiers instead of display names.
- Add pipeline preflight before GUI cancellation improvements so user-facing messages can call the same backend diagnostics.
- Fix visible cancellation before auxiliary worker cleanup so tests can assert consistent activity messages.
- Add query indexes before throttling harmony analysis; caching works better with a stable query API.
- Expand mypy and coverage only after the touched modules have stable tests.

## Campaign Self-Review

- Spec coverage: every audit category is mapped to exactly one plan.
- Placeholder scan: no task depends on undefined future behavior; broader architecture migrations are explicitly out of scope.
- Type consistency: `stem_id`, `safe_stem_key`, `PreflightReport`, auxiliary job lifecycle state, and `NoteIndex` names are introduced in their owning plans and reused consistently.
