from pathlib import Path

import pytest

from pitchstems.editor_project import EditorProject, EditorTrack, NoteEvent, midi_velocity_energy
from pitchstems.harmony_inspector import (
    chord_analysis_track_names,
    chord_base_pitch_weights,
    chord_note_constraints,
    chord_sample_text,
    filtered_chord_analysis_notes,
    harmony_context_key,
    resolve_notation_preference,
    selected_chord_analysis_notes,
)


def _project(tmp_path: Path) -> EditorProject:
    return EditorProject(
        project_dir=tmp_path,
        source_audio=tmp_path / "song.wav",
        tracks=[
            EditorTrack("bass", tmp_path / "bass.wav"),
            EditorTrack("piano", tmp_path / "piano.wav"),
            EditorTrack("drums", tmp_path / "drums.wav"),
        ],
        notes=[
            NoteEvent("bass", 0.0, 2.0, 43, 80),
            NoteEvent("bass", 0.5, 1.5, 55, 40),
            NoteEvent("piano", 0.25, 1.25, 47, 64),
        ],
        chords=[],
        duration=2.0,
    )


def test_resolve_notation_preference_prefers_user_then_theory_then_chord() -> None:
    assert resolve_notation_preference("flat", "G major", "F#") == "flat"
    assert resolve_notation_preference("auto", "Bb major", "F#") == "flat"
    assert resolve_notation_preference("auto", None, "F#") == "sharp"


def test_harmony_context_key_rounds_point_and_selection() -> None:
    assert harmony_context_key(12.345, None) == ("point", 12.35)
    assert harmony_context_key(12.345, (1.23456, 2.34567)) == ("selection", 1.235, 2.346)


def test_selected_chord_analysis_notes_filters_by_selected_tracks(tmp_path: Path) -> None:
    project = _project(tmp_path)

    assert len(selected_chord_analysis_notes(project, None)) == 3
    assert [note.stem for note in selected_chord_analysis_notes(project, {"piano"})] == ["piano"]


def test_chord_analysis_track_names_omits_tracks_without_notes_when_no_selection(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)

    assert chord_analysis_track_names(project, None) == ["bass", "piano"]
    assert chord_analysis_track_names(project, {"drums", "bass"}) == ["bass", "drums"]


def test_chord_sample_text_explains_track_sampling() -> None:
    assert chord_sample_text([], 0) == "Sample: no tracks selected. Tick Chord to include a track."
    assert chord_sample_text(["bass", "piano"], 42) == (
        "Sample: bass, piano (42 MIDI notes). View, Audio, and MIDI ticks do not affect detection."
    )


def test_chord_note_constraints_and_filtering() -> None:
    required, excluded = chord_note_constraints({0: "force", 7: "exclude", 2: "auto"})

    assert required == {0}
    assert excluded == {7}
    notes = [
        NoteEvent("bass", 0.0, 1.0, 43, 80),
        NoteEvent("piano", 0.0, 1.0, 60, 80),
    ]
    assert [note.pitch for note in filtered_chord_analysis_notes(notes, excluded)] == [60]


def test_selection_weights_sum_overlap_times_velocity_energy() -> None:
    notes = [
        NoteEvent("bass", 0.0, 2.0, 43, 80),
        NoteEvent("piano", 0.5, 1.5, 55, 40),
        NoteEvent("piano", 0.0, 1.0, 47, 64),
    ]

    weights = chord_base_pitch_weights(notes, ("selection", 0.25, 1.25))

    g_energy = 1.0 * midi_velocity_energy(80) + 0.75 * midi_velocity_energy(40)
    b_energy = 0.75 * midi_velocity_energy(64)
    assert weights[7] == pytest.approx(1.0)
    assert weights[11] == pytest.approx(b_energy / g_energy)


def test_point_weights_sum_active_events_per_pitch_class() -> None:
    notes = [
        NoteEvent("bass", 0.0, 2.0, 43, 20),
        NoteEvent("piano", 0.0, 2.0, 55, 80),
        NoteEvent("piano", 0.0, 2.0, 47, 64),
    ]

    weights = chord_base_pitch_weights(notes, ("point", 1.0))

    assert weights[7] == pytest.approx(1.0)
    g_energy = midi_velocity_energy(20) + midi_velocity_energy(80)
    assert weights[11] == pytest.approx(midi_velocity_energy(64) / g_energy)
