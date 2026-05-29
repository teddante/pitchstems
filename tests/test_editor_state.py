from pathlib import Path

from pitchstems.editor_project import ChordRegion
from pitchstems.editor_state import (
    EditorStateSnapshot,
    load_editor_state,
    parse_chord_overrides,
    parse_chord_removals,
    save_editor_state_snapshot,
    serialize_chord_overrides,
    serialize_chord_removals,
)
from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import load_project_manifest, save_project_manifest


def test_parse_editor_chord_state_ignores_invalid_entries() -> None:
    state = {
        "chord_overrides": [
            {"start": 2, "end": 3, "label": "G", "confidence": 0.8},
            {"start": 5, "end": 4, "label": "bad"},
            {"start": "x", "end": 6, "label": "bad"},
            "bad",
        ],
        "chord_removals": [
            {"start": 0.5, "end": 1.0},
            {"start": 3.0, "end": 2.0},
            None,
        ],
    }

    assert parse_chord_overrides(state) == [ChordRegion(2.0, 3.0, "G", 0.8)]
    assert parse_chord_removals(state) == [(0.5, 1.0)]


def test_serialize_editor_chord_state_round_trips() -> None:
    chords = [ChordRegion(1.0, 2.0, "Cmaj7", 0.72)]
    removals = [(3.0, 4.5)]

    assert serialize_chord_overrides(chords) == [
        {"start": 1.0, "end": 2.0, "label": "Cmaj7", "confidence": 0.72}
    ]
    assert serialize_chord_removals(removals) == [{"start": 3.0, "end": 4.5}]


def test_save_editor_state_snapshot_preserves_pipeline_fields(tmp_path: Path) -> None:
    normalized = tmp_path / "work" / "song.wav"
    normalized.parent.mkdir(parents=True)
    normalized.write_bytes(b"wav")
    result = PipelineResult(
        project_dir=tmp_path,
        normalized_audio=normalized,
        stems=[],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )
    save_project_manifest(result, generate_midi=True, midi_policy="all")

    save_editor_state_snapshot(
        result,
        EditorStateSnapshot(
            track_visibility={"bass": True},
            track_analysis_enabled={"bass": True},
            track_audio_enabled={"bass": False},
            track_audio_volume={"bass": 67},
            track_midi_enabled={"bass": True},
            track_midi_volume={"bass": 74},
            notation_spelling="flat",
            playhead_seconds=12.25,
            chord_overrides=[{"start": 1.0, "end": 2.0, "label": "G", "confidence": 1.0}],
            chord_removals=[{"start": 3.0, "end": 4.0}],
        ),
    )

    manifest = load_project_manifest(tmp_path)

    assert manifest["settings"]["generate_midi"] is True
    assert manifest["settings"]["midi_policy"] == "all"
    assert manifest["editor"]["notation_spelling"] == "flat"
    assert manifest["editor"]["playhead_seconds"] == 12.25
    assert load_editor_state(tmp_path)["track_audio_volume"] == {"bass": 67}
