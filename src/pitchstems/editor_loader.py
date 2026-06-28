from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pitchstems.editor_project import ChordRegion, EditorProject, build_editor_project
from pitchstems.editor_state import load_editor_state, parse_chord_overrides, parse_chord_removals
from pitchstems.pipeline_models import PipelineResult


@dataclass(frozen=True)
class EditorLoadResult:
    pipeline_result: PipelineResult
    base_project: EditorProject
    editor_project: EditorProject
    editor_state: dict[str, Any]
    manual_chords: list[ChordRegion]
    removed_chord_ranges: list[tuple[float, float]]


def build_editor_load_result(result: PipelineResult) -> EditorLoadResult:
    base_project = build_editor_project(result)
    editor_state = load_editor_state(result.project_dir)
    manual_chords = parse_chord_overrides(editor_state)
    removed_chord_ranges = parse_chord_removals(editor_state)
    editor_project = apply_chord_edits(base_project, manual_chords, removed_chord_ranges)
    return EditorLoadResult(
        pipeline_result=result,
        base_project=base_project,
        editor_project=editor_project,
        editor_state=editor_state,
        manual_chords=manual_chords,
        removed_chord_ranges=removed_chord_ranges,
    )


def apply_chord_edits(
    project: EditorProject,
    manual_chords: list[ChordRegion],
    removed_chord_ranges: list[tuple[float, float]],
) -> EditorProject:
    if not manual_chords and not removed_chord_ranges:
        return project
    chords = list(project.chords)
    for start, end in removed_chord_ranges:
        chords = _subtract_chord_range(chords, start, end)
    for manual in manual_chords:
        chords = _subtract_chord_range(chords, manual.start, manual.end)
        chords.append(manual)
    return replace(
        project,
        chords=sorted(chords, key=lambda chord: (chord.start, chord.end, chord.label)),
    )


def _subtract_chord_range(
    chords: list[ChordRegion],
    start: float,
    end: float,
) -> list[ChordRegion]:
    if end <= start:
        return chords
    edited: list[ChordRegion] = []
    for chord in chords:
        if chord.end <= start or chord.start >= end:
            edited.append(chord)
            continue
        if chord.start < start:
            edited.append(
                ChordRegion(
                    start=chord.start,
                    end=start,
                    label=chord.label,
                    confidence=chord.confidence,
                )
            )
        if chord.end > end:
            edited.append(
                ChordRegion(
                    start=end,
                    end=chord.end,
                    label=chord.label,
                    confidence=chord.confidence,
                )
            )
    return edited
