# Timeline Performance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make timeline redraw and note/chord lookup behavior measurable and bounded for dense MIDI projects.

**Architecture:** Add pure policies and benchmarks before changing Qt drawing. Keep `TimelineView` behavior intact while moving threshold decisions and query indexing into small tested modules.

**Tech Stack:** Python 3.10, PySide6, pytest, bisect-indexed query helpers.

---

## File Structure

- Create: `src/pitchstems/timeline_render_policy.py` for dense-render and tooltip thresholds.
- Modify: `src/pitchstems/gui_timeline.py` to consume `TimelineRenderPolicy`.
- Modify: `src/pitchstems/editor_query.py` to improve chord lookup and expose query counts where useful.
- Test: `tests/test_timeline_render_policy.py`, `tests/test_editor_query.py`, optional local benchmark script.

### Task 1: Extract Timeline Render Thresholds

**Files:**
- Create: `src/pitchstems/timeline_render_policy.py`
- Test: `tests/test_timeline_render_policy.py`

- [ ] **Step 1: Write failing tests**

```python
from pitchstems.timeline_render_policy import TimelineRenderPolicy


def test_timeline_render_policy_uses_dense_mode_for_many_visible_notes() -> None:
    policy = TimelineRenderPolicy(pixels_per_second=92, visible_note_count=2500)

    assert policy.dense_render is True
    assert policy.enable_tooltips is False
    assert policy.draw_note_labels is False


def test_timeline_render_policy_shows_labels_only_when_zoomed_and_sparse() -> None:
    policy = TimelineRenderPolicy(pixels_per_second=160, visible_note_count=120)

    assert policy.dense_render is False
    assert policy.enable_tooltips is True
    assert policy.draw_note_labels is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_timeline_render_policy.py -q`
Expected: FAIL because `pitchstems.timeline_render_policy` does not exist.

- [ ] **Step 3: Implement policy**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineRenderPolicy:
    pixels_per_second: float
    visible_note_count: int

    @property
    def draw_note_labels(self) -> bool:
        return self.pixels_per_second >= 150 and self.visible_note_count <= 900

    @property
    def dense_render(self) -> bool:
        return self.pixels_per_second < 55 or self.visible_note_count > 2400

    @property
    def enable_tooltips(self) -> bool:
        return self.visible_note_count <= 1400 and not self.dense_render
```

- [ ] **Step 4: Verify tests pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_timeline_render_policy.py -q`
Expected: PASS.

### Task 2: Use Render Policy In TimelineView

**Files:**
- Modify: `src/pitchstems/gui_timeline.py`
- Test: `tests/test_timeline_render_policy.py`, GUI smoke

- [ ] **Step 1: Replace inline threshold logic**

Import:

```python
from pitchstems.timeline_render_policy import TimelineRenderPolicy
```

In `_draw_tracks`, replace the three threshold assignments with:

```python
policy = TimelineRenderPolicy(
    pixels_per_second=self.pixels_per_second,
    visible_note_count=visible_note_count,
)
draw_note_labels = policy.draw_note_labels
dense_render = policy.dense_render
enable_tooltips = policy.enable_tooltips
```

- [ ] **Step 2: Verify timeline tests and smoke**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_timeline_render_policy.py tests/test_gui_timeline.py -q
$env:QT_QPA_PLATFORM="offscreen"
$env:PITCHSTEMS_GUI_SMOKE="project"
.\.venv\Scripts\python.exe -c "from pitchstems.app import main; raise SystemExit(main())"
```

Expected: tests pass and GUI smoke exits 0.

### Task 3: Improve ChordIndex Lookup

**Files:**
- Modify: `src/pitchstems/editor_query.py`
- Test: `tests/test_editor_query.py`

- [ ] **Step 1: Add tests for ordered lookup**

Append to `tests/test_editor_query.py`:

```python
from pitchstems.editor_models import ChordRegion
from pitchstems.editor_query import ChordIndex


def test_chord_index_uses_ordered_starts_for_active_lookup() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.9),
        ChordRegion(2.0, 3.0, "G", 0.8),
        ChordRegion(4.0, 5.0, "Am", 0.7),
    ]
    index = ChordIndex(chords, duration=6.0)

    assert index.active_at(2.5) == chords[1]
    assert index.active_at(3.5) is None
    assert index.gap_at(3.5) == (3.0, 4.0)
```

- [ ] **Step 2: Implement indexed starts**

Update `ChordIndex.__init__`:

```python
self.chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
self.starts = [chord.start for chord in self.chords]
self.duration = duration
```

Update `active_at`:

```python
right = bisect_right(self.starts, seconds)
for chord in reversed(self.chords[:right]):
    if chord.start <= seconds < chord.end:
        return chord
    if chord.end <= seconds:
        break
return None
```

Update `gap_at`:

```python
if self.active_at(seconds) is not None:
    return None
right = bisect_right(self.starts, seconds)
previous = None
for chord in reversed(self.chords[:right]):
    if chord.end <= seconds:
        previous = chord
        break
next_chord = self.chords[right] if right < len(self.chords) else None
start = previous.end if previous else 0.0
end = next_chord.start if next_chord else self.duration
return (start, end) if end - start >= 0.05 else None
```

- [ ] **Step 3: Verify query tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_editor_query.py tests/test_editor_project.py -q`
Expected: PASS.

### Task 4: Add Dense Timeline Benchmark Guard

**Files:**
- Create: `tests/test_timeline_performance.py`

- [ ] **Step 1: Add bounded query performance test**

```python
from pitchstems.editor_models import NoteEvent
from pitchstems.editor_query import NoteIndex


def test_note_index_handles_dense_active_query_quickly() -> None:
    notes = [
        NoteEvent(stem="piano", start=index * 0.01, end=index * 0.01 + 0.5, pitch=60 + index % 24, velocity=80)
        for index in range(10_000)
    ]
    index = NoteIndex(notes)

    active = index.active_at(50.0)

    assert active
    assert all(note.start <= 50.0 < note.end for note in active)
```

- [ ] **Step 2: Verify performance test is stable**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_timeline_performance.py -q`
Expected: PASS in under one second on the local dev machine. If it is slower, inspect query behavior before changing the threshold or assertion.

### Task 5: Full Verification And Commit

- [ ] **Step 1: Run project gate**

Run: `.\scripts\check.ps1 -GuiSmoke`
Expected: PASS.

- [ ] **Step 2: Commit**

```powershell
git add src/pitchstems/timeline_render_policy.py src/pitchstems/gui_timeline.py src/pitchstems/editor_query.py tests/test_timeline_render_policy.py tests/test_editor_query.py tests/test_timeline_performance.py
git commit -m "perf: harden timeline rendering and query policies"
```

## Self-Review

- Spec coverage: covers timeline redraw thresholds and indexed note/chord query risks.
- Placeholder scan: every new function and class is named and defined.
- Type consistency: `TimelineRenderPolicy` is the only new timeline rendering contract.
