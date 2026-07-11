from pathlib import Path
import wave

from mido import Message, MidiFile, MidiTrack

from pitchstems.editor_loader import apply_chord_edits, build_editor_load_result
from pitchstems.editor_project import ChordRegion, EditorProject
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult
from pitchstems.project_store import save_project_manifest


def test_apply_chord_edits_replaces_only_overlapping_time_ranges() -> None:
    project = EditorProject(
        project_dir=Path("."),
        source_audio=Path("song.wav"),
        duration=4.0,
        tracks=[],
        notes=[],
        chords=[
            ChordRegion(0.0, 1.0, "C", 0.8),
            ChordRegion(1.0, 2.0, "G", 0.8),
            ChordRegion(3.0, 4.0, "F", 0.8),
        ],
    )

    edited = apply_chord_edits(
        project,
        [ChordRegion(0.5, 1.5, "Am", 1.0)],
        [(2.8, 4.2)],
    )

    assert edited.chords == [
        ChordRegion(0.0, 0.5, "C", 0.8),
        ChordRegion(0.5, 1.5, "Am", 1.0),
        ChordRegion(1.5, 2.0, "G", 0.8),
    ]
    assert project.chords[0].label == "C"


def test_apply_chord_edits_splits_removed_middle_ranges() -> None:
    project = EditorProject(
        project_dir=Path("."),
        source_audio=Path("song.wav"),
        duration=4.0,
        tracks=[],
        notes=[],
        chords=[ChordRegion(0.0, 4.0, "C", 0.8)],
    )

    edited = apply_chord_edits(project, [], [(1.0, 2.0)])

    assert edited.chords == [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(2.0, 4.0, "C", 0.8),
    ]


def test_build_editor_load_result_applies_manifest_editor_state(tmp_path: Path) -> None:
    stem_path = tmp_path / "stems" / "song_piano.wav"
    midi_path = tmp_path / "midi" / "piano" / "song_piano.mid"
    normalized = tmp_path / "work" / "song.wav"
    _write_wav(stem_path, 1.0)
    _write_wav(normalized, 1.0)
    _write_midi(midi_path)
    result = PipelineResult(
        project_dir=tmp_path,
        normalized_audio=normalized,
        stems=[StemResult("piano", stem_path)],
        midi_files=[MidiResult("piano", midi_path)],
        combined_midi=None,
        zip_path=None,
    )
    save_project_manifest(
        result,
        generate_chord_suggestions=False,
        chord_overrides=[{"start": 0.0, "end": 1.0, "label": "C", "confidence": 0.9}],
        track_visibility={"piano": False},
        playhead_seconds=0.25,
    )

    loaded = build_editor_load_result(result)

    assert loaded.pipeline_result == result
    assert loaded.editor_state["track_visibility"] == {"piano": False}
    assert loaded.manual_chords == [ChordRegion(0.0, 1.0, "C", 0.9)]
    assert loaded.editor_project.chords == [ChordRegion(0.0, 1.0, "C", 0.9)]
    assert loaded.base_project.chords == []


def _write_midi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    track.append(Message("note_on", note=60, velocity=90, time=0))
    track.append(Message("note_off", note=60, velocity=0, time=480))
    midi.tracks.append(track)
    midi.save(path)


def _write_wav(path: Path, duration_seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 8000
    frames = b"\x00\x00" * int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
