from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from pitchstems.editor_project import ChordRegion
from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import PROJECT_FILENAME, load_project_manifest, save_project_manifest


@dataclass(frozen=True)
class EditorStateSnapshot:
    track_visibility: dict[str, bool]
    track_analysis_enabled: dict[str, bool]
    track_audio_enabled: dict[str, bool]
    track_audio_volume: dict[str, int]
    track_midi_enabled: dict[str, bool]
    track_midi_volume: dict[str, int]
    notation_spelling: str
    playhead_seconds: float
    chord_overrides: list[dict[str, Any]]
    chord_removals: list[dict[str, float]]


def load_editor_state(project_dir: Path) -> dict[str, Any]:
    try:
        manifest = load_project_manifest(project_dir / PROJECT_FILENAME)
    except Exception:
        return {}
    editor = manifest.get("editor", {})
    return editor if isinstance(editor, dict) else {}


def parse_chord_overrides(editor_state: Mapping[str, Any]) -> list[ChordRegion]:
    chords: list[ChordRegion] = []
    for item in editor_state.get("chord_overrides", []):
        if not isinstance(item, Mapping):
            continue
        try:
            start = float(item.get("start", 0.0))
            end = float(item.get("end", 0.0))
            label = str(item.get("label", "")).strip()
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            continue
        if label and _valid_time_range(start, end):
            confidence = _clamp_confidence(confidence)
            chords.append(ChordRegion(start=start, end=end, label=label, confidence=confidence))
    return sorted(chords, key=lambda chord: (chord.start, chord.end, chord.label))


def parse_chord_removals(editor_state: Mapping[str, Any]) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []
    for item in editor_state.get("chord_removals", []):
        if not isinstance(item, Mapping):
            continue
        try:
            start = float(item.get("start", 0.0))
            end = float(item.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if _valid_time_range(start, end):
            ranges.append((start, end))
    return sorted(ranges)


def serialize_chord_overrides(chords: list[ChordRegion]) -> list[dict[str, Any]]:
    return [
        {
            "start": chord.start,
            "end": chord.end,
            "label": chord.label,
            "confidence": chord.confidence,
        }
        for chord in chords
    ]


def serialize_chord_removals(ranges: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"start": start, "end": end} for start, end in ranges]


def _valid_time_range(start: float, end: float) -> bool:
    return isfinite(start) and isfinite(end) and start >= 0.0 and end > start


def _clamp_confidence(confidence: float) -> float:
    if not isfinite(confidence):
        return 1.0
    return max(0.0, min(1.0, confidence))


def build_editor_state_snapshot(
    *,
    track_visibility_checks: Mapping[str, Any],
    track_analysis_checks: Mapping[str, Any],
    track_audio_checks: Mapping[str, Any],
    track_audio_sliders: Mapping[str, Any],
    track_midi_checks: Mapping[str, Any],
    track_midi_sliders: Mapping[str, Any],
    notation_spelling: str,
    playhead_seconds: float,
    manual_chords: list[ChordRegion],
    removed_chord_ranges: list[tuple[float, float]],
) -> EditorStateSnapshot:
    return EditorStateSnapshot(
        track_visibility=_checked_map(track_visibility_checks),
        track_analysis_enabled=_checked_map(track_analysis_checks),
        track_audio_enabled=_checked_map(track_audio_checks),
        track_audio_volume=_value_map(track_audio_sliders),
        track_midi_enabled=_checked_map(track_midi_checks),
        track_midi_volume=_value_map(track_midi_sliders),
        notation_spelling=notation_spelling,
        playhead_seconds=playhead_seconds,
        chord_overrides=serialize_chord_overrides(manual_chords),
        chord_removals=serialize_chord_removals(removed_chord_ranges),
    )


def _checked_map(widgets: Mapping[str, Any]) -> dict[str, bool]:
    return {
        stem_name: bool(widget.isChecked())
        for stem_name, widget in widgets.items()
    }


def _value_map(widgets: Mapping[str, Any]) -> dict[str, int]:
    return {
        stem_name: int(widget.value())
        for stem_name, widget in widgets.items()
    }


def save_editor_state_snapshot(result: PipelineResult, snapshot: EditorStateSnapshot) -> Path:
    return save_project_manifest(
        result,
        track_visibility=snapshot.track_visibility,
        track_analysis_enabled=snapshot.track_analysis_enabled,
        track_audio_enabled=snapshot.track_audio_enabled,
        track_audio_volume=snapshot.track_audio_volume,
        track_midi_enabled=snapshot.track_midi_enabled,
        track_midi_volume=snapshot.track_midi_volume,
        notation_spelling=snapshot.notation_spelling,
        playhead_seconds=snapshot.playhead_seconds,
        chord_overrides=snapshot.chord_overrides,
        chord_removals=snapshot.chord_removals,
    )
