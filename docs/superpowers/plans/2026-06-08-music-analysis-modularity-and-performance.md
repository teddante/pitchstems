# Music Analysis Modularity And Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split chord/theory analysis into smaller modules and add indexed note/chord queries for editor interactions.

**Architecture:** Keep `pitchstems.chord_analysis` and `pitchstems.editor_project` compatibility exports stable. Move scoring, detection, and explanation internals into focused modules, then introduce a `NoteIndex` used by harmony/theory flows without changing user-visible chord labels.

**Tech Stack:** Python dataclasses, bisect, pytest.

---

## Files

- Create: `src/pitchstems/chord_scoring.py`
- Create: `src/pitchstems/chord_detection.py`
- Create: `src/pitchstems/chord_explanation.py`
- Create: `src/pitchstems/editor_query.py`
- Modify: `src/pitchstems/chord_analysis.py`
- Modify: `src/pitchstems/scale_analysis.py`
- Modify: `src/pitchstems/editor_project.py`
- Modify: `src/pitchstems/gui_harmony_flow.py`
- Test: `tests/test_chord_analysis.py`
- Test: `tests/test_editor_project.py`
- Create: `tests/test_editor_query.py`

## Task 1: Add Golden Behavior Tests Before Refactor

- [ ] **Step 1: Add focused chord scoring tests**

Add to `tests/test_chord_analysis.py`:

```python
def test_weighted_chord_analysis_keeps_existing_cmaj7_behavior() -> None:
    notes = [
        NoteEvent("piano", 0.0, 1.0, 60, 100),
        NoteEvent("piano", 0.0, 1.0, 64, 90),
        NoteEvent("piano", 0.0, 1.0, 67, 90),
        NoteEvent("piano", 0.0, 1.0, 71, 70),
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)

    assert analysis.label == "Cmaj7"
    assert analysis.candidates[0][0] == "Cmaj7"
    assert analysis.candidate_explanations["Cmaj7"]
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_chord_analysis.py::test_weighted_chord_analysis_keeps_existing_cmaj7_behavior -q`

Expected: PASS before refactor.

- [ ] **Step 2: Add interval query tests**

Create `tests/test_editor_query.py`:

```python
from __future__ import annotations

from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.editor_query import NoteIndex, ChordIndex


def test_note_index_returns_notes_active_at_time() -> None:
    notes = [
        NoteEvent("piano", 0.0, 1.0, 60, 90),
        NoteEvent("bass", 2.0, 3.0, 40, 90),
    ]
    index = NoteIndex(notes)
    assert index.active_at(0.5) == [notes[0]]
    assert index.active_at(2.5) == [notes[1]]


def test_chord_index_returns_gap_between_chords() -> None:
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(2.0, 3.0, "G", 0.8),
    ]
    index = ChordIndex(chords, duration=4.0)
    assert index.gap_at(1.5) == (1.0, 2.0)
    assert index.gap_at(0.5) is None
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_editor_query.py -q`

Expected: FAIL because indexes do not exist.

## Task 2: Add Editor Query Indexes

- [ ] **Step 1: Implement indexes**

Create `src/pitchstems/editor_query.py`:

```python
from __future__ import annotations

from bisect import bisect_right

from pitchstems.editor_models import ChordRegion, NoteEvent


class NoteIndex:
    def __init__(self, notes: list[NoteEvent]) -> None:
        self.notes = sorted(notes, key=lambda note: (note.start, note.end, note.stem, note.pitch))
        self.starts = [note.start for note in self.notes]

    def active_at(self, seconds: float) -> list[NoteEvent]:
        end = bisect_right(self.starts, seconds)
        return [note for note in self.notes[:end] if note.end > seconds]

    def overlapping(self, start: float, end: float) -> list[NoteEvent]:
        right = bisect_right(self.starts, end)
        return [note for note in self.notes[:right] if note.end > start]


class ChordIndex:
    def __init__(self, chords: list[ChordRegion], duration: float) -> None:
        self.chords = sorted(chords, key=lambda chord: (chord.start, chord.end))
        self.duration = duration

    def active_at(self, seconds: float) -> ChordRegion | None:
        for chord in self.chords:
            if chord.start <= seconds < chord.end:
                return chord
        return None

    def gap_at(self, seconds: float) -> tuple[float, float] | None:
        if self.active_at(seconds) is not None:
            return None
        previous = max((chord for chord in self.chords if chord.end <= seconds), key=lambda chord: chord.end, default=None)
        next_chord = min((chord for chord in self.chords if chord.start >= seconds), key=lambda chord: chord.start, default=None)
        start = previous.end if previous else 0.0
        end = next_chord.start if next_chord else self.duration
        return (start, end) if end - start >= 0.05 else None
```

- [ ] **Step 2: Verify indexes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_editor_query.py -q`

Expected: PASS.

## Task 3: Extract Chord Scoring And Detection

- [ ] **Step 1: Move weighted scoring helpers**

Create `src/pitchstems/chord_scoring.py` and move these functions/classes from `chord_analysis.py`:

```python
ChordScoringOptions
PartialChordCandidate
_score_root_candidates
_score_weighted_root_candidates
_partial_shell_candidates
_partial_shell_candidates_from_weights
_candidate_explanation
_weighted_candidate_explanation
_label_matches_constraints
```

Keep imports from `pitchstems.chord_naming`, `pitchstems.notation`, and `pitchstems.editor_models`.

- [ ] **Step 2: Move detection helpers**

Create `src/pitchstems/chord_detection.py` and move:

```python
detect_chords
active_notes_at
analyze_chord_at
analyze_chord_region
midi_velocity_energy
```

Leave `analyze_chord()` in `chord_analysis.py` if it remains the simple public facade, or move it into `chord_detection.py` and re-export it from `chord_analysis.py`.

- [ ] **Step 3: Move explanation-only helpers**

Create `src/pitchstems/chord_explanation.py` and move:

```python
partial_harmony_hints
_interval_quality_name
_interval_names
_ordered_pitch_classes
```

- [ ] **Step 4: Keep compatibility exports**

In `src/pitchstems/chord_analysis.py`, re-export the public API:

```python
from pitchstems.chord_detection import active_notes_at, analyze_chord, analyze_chord_at, analyze_chord_region, detect_chords, midi_velocity_energy
from pitchstems.chord_explanation import partial_harmony_hints
from pitchstems.chord_scoring import ChordScoringOptions, PartialChordCandidate
```

Preserve `__all__` names already used by `editor_project.py`.

- [ ] **Step 5: Verify behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chord_analysis.py tests/test_editor_project.py tests/test_theory.py -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 4: Use Query Indexes In Editor Project And Harmony Flow

- [ ] **Step 1: Add indexes to `EditorProject`**

In `src/pitchstems/editor_project.py`:

```python
from pitchstems.editor_query import ChordIndex, NoteIndex

@dataclass(frozen=True)
class EditorProject:
    project_dir: Path
    source_audio: Path
    tracks: list[EditorTrack]
    notes: list[NoteEvent]
    chords: list[ChordRegion]
    duration: float

    @property
    def note_index(self) -> NoteIndex:
        return NoteIndex(self.notes)

    @property
    def chord_index(self) -> ChordIndex:
        return ChordIndex(self.chords, self.duration)
```

If repeated property construction is too slow, use `functools.cached_property` and remove `frozen=True` from `EditorProject` only if tests require it.

- [ ] **Step 2: Replace direct scans**

In `src/pitchstems/gui_harmony_flow.py`, use:

```python
notes = window.editor_project.note_index.active_at(seconds)
```

For selected regions:

```python
notes = window.editor_project.note_index.overlapping(start, end)
```

In `app.current_chord_gap_range()`, use:

```python
return self.editor_project.chord_index.gap_at(position)
```

- [ ] **Step 3: Verify**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_editor_query.py tests/test_editor_project.py tests/test_harmony_inspector.py tests/test_gui_transport.py -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 5: Commit Music Analysis Work

- [ ] **Step 1: Review diff**

Run: `git diff --stat`

Expected: `chord_analysis.py` is smaller, new focused modules exist, public tests still pass.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src\pitchstems\chord_scoring.py src\pitchstems\chord_detection.py src\pitchstems\chord_explanation.py src\pitchstems\editor_query.py src\pitchstems\chord_analysis.py src\pitchstems\scale_analysis.py src\pitchstems\editor_project.py src\pitchstems\gui_harmony_flow.py tests\test_chord_analysis.py tests\test_editor_project.py tests\test_editor_query.py tests\test_theory.py
git commit -m "refactor: split music analysis and index editor queries"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers chord/theory modularity and large-project query performance.
- Placeholder scan: module ownership and moved symbols are explicit.
- Type consistency: `NoteIndex` and `ChordIndex` are the query APIs.
