from pathlib import Path
import wave

from mido import Message, MetaMessage, MidiFile, MidiTrack
import pytest

from pitchstems.editor_project import (
    ChordRegion,
    ChordScoringOptions,
    EditorProject,
    EditorTrack,
    NoteEvent,
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    analyze_chord_region,
    build_editor_project,
    chord_tones_for_label,
    detect_chords,
    exact_chord_names_for_pitch_classes,
    identify_chord,
    midi_velocity_energy,
    midi_note_name,
    read_midi_notes,
)
from pitchstems.pipeline import PipelineResult
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


def test_read_midi_notes_returns_absolute_seconds(tmp_path: Path) -> None:
    path = tmp_path / "bass.mid"
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    track.append(MetaMessage("set_tempo", tempo=500000, time=0))
    track.append(Message("note_on", note=40, velocity=90, time=0))
    track.append(Message("note_off", note=40, velocity=0, time=480))
    midi.tracks.append(track)
    midi.save(path)

    notes = read_midi_notes(path, "bass")

    assert len(notes) == 1
    assert notes[0].stem == "bass"
    assert notes[0].start == 0
    assert notes[0].end == 0.5
    assert notes[0].name == "E2"


def test_build_editor_project_uses_audio_duration_when_midi_is_empty(tmp_path: Path) -> None:
    normalized = tmp_path / "work" / "song.wav"
    stem_path = tmp_path / "stems" / "song_bass.wav"
    _write_wav(normalized, duration_seconds=1.0)
    _write_wav(stem_path, duration_seconds=2.25)
    result = PipelineResult(
        project_dir=tmp_path,
        normalized_audio=normalized,
        stems=[StemResult("bass", stem_path)],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )

    project = build_editor_project(result)

    assert project.duration == 2.25
    assert project.tracks[0].audio_path == stem_path
    assert project.notes == []


def test_editor_project_exposes_query_indexes(tmp_path: Path) -> None:
    note = NoteEvent("piano", 0.0, 1.0, 60, 90)
    chords = [
        ChordRegion(0.0, 1.0, "C", 0.8),
        ChordRegion(2.0, 3.0, "G", 0.8),
    ]
    project = EditorProject(
        project_dir=tmp_path,
        source_audio=tmp_path / "song.wav",
        tracks=[EditorTrack("piano", tmp_path / "piano.wav")],
        notes=[note],
        chords=chords,
        duration=4.0,
    )

    assert project.note_index.active_at(0.5) == [note]
    assert project.chord_index.gap_at(1.5) == (1.0, 2.0)


def test_editor_project_reuses_query_indexes(tmp_path: Path, monkeypatch) -> None:
    import pitchstems.editor_project as editor_project_module

    note = NoteEvent("piano", 0.0, 1.0, 60, 90)
    project = EditorProject(
        project_dir=tmp_path,
        source_audio=tmp_path / "song.wav",
        tracks=[EditorTrack("piano", tmp_path / "piano.wav")],
        notes=[note],
        chords=[ChordRegion(0.0, 1.0, "C", 0.8)],
        duration=1.0,
    )
    note_index_calls = 0
    chord_index_calls = 0

    class CountingNoteIndex:
        def __init__(self, notes):
            nonlocal note_index_calls
            note_index_calls += 1
            self.notes = notes

    class CountingChordIndex:
        def __init__(self, chords, duration):
            nonlocal chord_index_calls
            chord_index_calls += 1
            self.chords = chords
            self.duration = duration

    monkeypatch.setattr(editor_project_module, "NoteIndex", CountingNoteIndex)
    monkeypatch.setattr(editor_project_module, "ChordIndex", CountingChordIndex)

    assert project.note_index is project.note_index
    assert project.chord_index is project.chord_index
    assert note_index_calls == 1
    assert chord_index_calls == 1


def test_build_editor_project_skips_missing_or_corrupt_midi(tmp_path: Path) -> None:
    normalized = tmp_path / "work" / "song.wav"
    stem_path = tmp_path / "stems" / "song_bass.wav"
    corrupt_midi = tmp_path / "midi" / "corrupt.mid"
    _write_wav(normalized, duration_seconds=1.0)
    _write_wav(stem_path, duration_seconds=1.5)
    corrupt_midi.parent.mkdir(parents=True)
    corrupt_midi.write_text("not midi", encoding="utf-8")
    result = PipelineResult(
        project_dir=tmp_path,
        normalized_audio=normalized,
        stems=[StemResult("bass", stem_path)],
        midi_files=[
            MidiResult("bass", tmp_path / "midi" / "missing.mid"),
            MidiResult("bass", corrupt_midi),
        ],
        combined_midi=None,
        zip_path=None,
    )

    project = build_editor_project(result)

    assert project.duration == 1.5
    assert project.tracks[0].name == "bass"
    assert project.notes == []


def test_read_midi_notes_uses_global_format_one_tempo_map(tmp_path: Path) -> None:
    path = tmp_path / "tempo-map.mid"
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo_track = MidiTrack()
    tempo_track.append(MetaMessage("set_tempo", tempo=1_000_000, time=0))
    note_track = MidiTrack()
    note_track.append(Message("note_on", note=60, velocity=90, time=0))
    note_track.append(Message("note_off", note=60, velocity=0, time=480))
    midi.tracks.extend([tempo_track, note_track])
    midi.save(path)

    notes = read_midi_notes(path, "piano")

    assert len(notes) == 1
    assert notes[0].start == 0
    assert notes[0].end == 1.0


def test_read_midi_notes_applies_tempo_changes_across_note_tracks(tmp_path: Path) -> None:
    path = tmp_path / "tempo-change.mid"
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo_track = MidiTrack()
    tempo_track.append(MetaMessage("set_tempo", tempo=500_000, time=0))
    tempo_track.append(MetaMessage("set_tempo", tempo=1_000_000, time=480))
    note_track = MidiTrack()
    note_track.append(Message("note_on", note=60, velocity=90, time=0))
    note_track.append(Message("note_off", note=60, velocity=0, time=960))
    midi.tracks.extend([tempo_track, note_track])
    midi.save(path)

    notes = read_midi_notes(path, "piano")

    assert len(notes) == 1
    assert notes[0].start == 0
    assert notes[0].end == 1.5


def test_identify_chord_names_common_triads() -> None:
    assert identify_chord([60, 64, 67])[0] == "C"
    assert identify_chord([57, 60, 64])[0] == "Am"
    assert identify_chord([62, 65, 68])[0] == "Ddim"


def test_analyze_chord_names_extensions_and_inversions() -> None:
    assert analyze_chord([60, 64, 67, 70]).label == "C7"
    assert analyze_chord([64, 67, 72]).label == "C/E"
    assert analyze_chord([60, 64, 67, 74]).label == "Cadd9"
    assert analyze_chord([60, 65, 67, 70]).label == "C7sus4"


def test_analyze_chord_names_omitted_third_major_ninth_sound() -> None:
    analysis = analyze_chord([55, 62, 66, 69], required_pitch_classes={2, 6, 7, 9})
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "Gmaj9(no3)"
    assert "Gmaj7sus2" in analysis.candidate_aliases["Gmaj9(no3)"]
    assert "Dadd4/G" in analysis.candidate_aliases["Gmaj9(no3)"]
    assert all({"G", "D", "F#", "A"} <= set(analysis.candidate_notes[label]) for label in labels)
    assert all("B" not in analysis.candidate_notes[label] for label in labels[:2])


def test_exact_chord_names_include_contextual_omitted_third_aliases() -> None:
    names = exact_chord_names_for_pitch_classes({2, 6, 7, 9}, bass=7)

    assert "Gmaj9(no3)" in names
    assert "Gmaj7sus2" in names
    assert "Dadd4/G" in names


def test_analyze_chord_includes_contextual_candidates() -> None:
    analysis = analyze_chord([60, 64, 67, 69])
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "C6"
    assert "C6" in labels
    assert analysis.candidate_notes["C6"] == ["C", "E", "G", "A"]
    assert "Am7/C" in analysis.candidate_aliases["C6"]
    assert any("Display score:" in line for line in analysis.candidate_explanations["C6"])
    assert any("Matched tones:" in line for line in analysis.candidate_explanations["C6"])


def test_chord_constraints_force_and_exclude_candidate_tones() -> None:
    forced = analyze_chord([60, 64, 67], required_pitch_classes={9})
    forced_labels = [label for label, _confidence in forced.candidates]

    assert "C6" in forced_labels
    assert forced_labels
    assert all("A" in forced.candidate_notes[label] for label in forced_labels)

    excluded = analyze_chord([60, 64, 67, 69], excluded_pitch_classes={9})

    assert excluded.candidates
    assert all("A" not in excluded.candidate_notes[label] for label, _confidence in excluded.candidates)


def test_chord_tones_for_label_orders_extensions_from_root() -> None:
    assert chord_tones_for_label("Cmaj9") == ["C", "E", "G", "B", "D"]
    assert chord_tones_for_label("F#7sus4/C#") == ["F#", "B", "C#", "E"]
    assert chord_tones_for_label("Gmaj9(no3)") == ["G", "D", "F#", "A"]
    assert chord_tones_for_label("Fm7(no5)") == ["F", "Ab", "Eb"]
    assert chord_tones_for_label("Ab6(no3)") == ["Ab", "Eb", "F"]


def test_analyze_chord_at_uses_notes_active_at_playhead() -> None:
    notes = [
        _note(0.0, 1.0, 60),
        _note(0.0, 1.0, 64),
        _note(0.0, 1.0, 67),
        _note(1.2, 2.0, 62),
    ]

    active = active_notes_at(notes, 0.5)
    analysis = analyze_chord_at(notes, 0.5)

    assert [note.name for note in active] == ["C4", "E4", "G4"]
    assert analysis.label == "C"
    assert analysis.active_note_names == ["C4", "E4", "G4"]
    assert analyze_chord_at(notes, 1.4).label is None


def test_analyze_chord_at_sums_duplicate_pitch_class_energy() -> None:
    notes = [
        _note(0.0, 1.0, 43, velocity=20),  # G
        _note(0.0, 1.0, 55, velocity=80),  # G
        _note(0.0, 1.0, 47, velocity=64),  # B
    ]

    analysis = analyze_chord_at(notes, 0.5)

    weights = dict(analysis.note_weights)
    expected_g_energy = midi_velocity_energy(20) + midi_velocity_energy(80)
    assert weights["G"] == 1.0
    assert weights["B"] == pytest.approx(midi_velocity_energy(64) / expected_g_energy)


def test_analyze_chord_region_weights_overlap_and_velocity() -> None:
    notes = [
        _note(0.0, 2.0, 60, velocity=100),
        _note(0.0, 2.0, 64, velocity=96),
        _note(0.0, 2.0, 67, velocity=92),
        _note(0.15, 0.25, 62, velocity=50),
    ]

    analysis = analyze_chord_region(notes, 0.0, 2.0)

    assert analysis.label == "C"
    assert analysis.note_weights[0][0] == "C"
    assert dict(analysis.note_weights)["D"] < 0.1
    assert any("weighted notes" in line for line in analysis.candidate_explanations["C"])
    assert any("candidate-tone energy" in line for line in analysis.candidate_explanations["C"])


def test_midi_velocity_energy_uses_power_from_velocity_amplitude() -> None:
    assert midi_velocity_energy(127) == 1.0
    assert midi_velocity_energy(0) == 0.0
    assert midi_velocity_energy(64) == (64 / 127) ** 2


def test_analyze_chord_region_can_name_ambiguous_selection_candidates() -> None:
    notes = [
        _note(0.0, 1.0, 60),
        _note(0.0, 1.0, 64),
        _note(0.0, 1.0, 67),
        _note(0.0, 1.0, 69),
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "C6"
    assert "C6" in labels
    assert "Am7/C" in analysis.candidate_aliases["C6"]


def test_energy_chord_scoring_prefers_strong_core_over_weak_color() -> None:
    notes = [
        _note(0.0, 0.68, 55, velocity=127),
        _note(0.0, 1.00, 62, velocity=127),
        _note(0.0, 0.37, 66, velocity=127),
        _note(0.0, 0.45, 69, velocity=127),
        _note(0.0, 0.18, 71, velocity=127),
        _note(0.0, 0.02, 68, velocity=127),
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)

    assert analysis.label == "Gmaj9(no3)"
    assert [name for name, _weight in analysis.note_weights] == ["D", "G", "A", "F#", "B", "Ab"]
    assert dict(analysis.note_weights)["B"] < dict(analysis.note_weights)["F#"]


def test_weighted_chord_candidates_reject_required_tones_with_no_visible_energy() -> None:
    notes = [
        _note(0.0, 1.00, 55, velocity=127),  # G
        _note(0.0, 0.30, 62, velocity=127),  # D
        _note(0.0, 0.20, 71, velocity=127),  # B
        _note(0.0, 0.01, 69, velocity=127),  # A
        _note(0.0, 0.001, 60, velocity=127),  # C, shown as 0%
        _note(0.0, 0.001, 64, velocity=127),  # E, shown as 0%
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "G"
    assert "Cmaj9(no3)/G" not in labels
    assert "Em7/G" not in labels


def test_weighted_chord_candidates_group_aliases_and_keep_colored_options() -> None:
    notes = [
        _note(0.0, 1.00, 55, velocity=127),  # G
        _note(0.0, 0.55, 62, velocity=127),  # D
        _note(0.0, 0.19, 66, velocity=127),  # F#
        _note(0.0, 0.17, 69, velocity=127),  # A
        _note(0.0, 0.13, 71, velocity=127),  # B
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)
    labels = [label for label, _confidence in analysis.candidates]
    note_sets = [
        frozenset(analysis.candidate_notes[label])
        for label in labels
    ]

    assert analysis.label == "Gsus2"
    assert "Gadd9(no3)" in analysis.candidate_aliases["Gsus2"]
    assert len(note_sets) == len(set(note_sets))
    assert any("F#" in analysis.candidate_notes[label] for label in labels)


def test_weighted_force_constrains_names_without_inventing_energy() -> None:
    notes = [
        _note(0.0, 1.0, 55, velocity=127),  # G
        _note(0.0, 1.0, 62, velocity=127),  # D
        _note(0.0, 1.0, 71, velocity=127),  # B
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0, required_pitch_classes={0})
    labels = [label for label, _confidence in analysis.candidates]

    assert labels
    assert all("C" in analysis.candidate_notes[label] for label in labels)
    assert "C" not in dict(analysis.note_weights)
    assert any("Missing tones: C" in line for line in analysis.candidate_explanations[labels[0]])


def test_weighted_force_can_complete_two_note_selection() -> None:
    notes = [
        _note(0.0, 1.0, 55, velocity=127),  # G
        _note(0.0, 1.0, 62, velocity=127),  # D
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0, required_pitch_classes={11})

    assert analysis.label == "G"
    assert analysis.candidate_notes["G"] == ["G", "B", "D"]


def test_playhead_force_can_complete_two_note_chord() -> None:
    notes = [
        _note(0.0, 1.0, 55),  # G
        _note(0.0, 1.0, 62),  # D
    ]

    analysis = analyze_chord_at(notes, 0.5, required_pitch_classes={11})

    assert analysis.label == "G"
    assert analysis.candidate_notes["G"] == ["G", "B", "D"]
    assert "B4" not in analysis.active_note_names


def test_weighted_note_floor_removes_trace_extensions_from_candidates() -> None:
    notes = [
        _note(0.0, 1.0, 60, velocity=127),  # C
        _note(0.0, 0.25, 67, velocity=127),  # G
        _note(0.0, 0.20, 64, velocity=127),  # E
        _note(0.0, 0.01, 71, velocity=127),  # B trace
    ]

    analysis = analyze_chord_region(
        notes,
        0.0,
        1.0,
        scoring_options=ChordScoringOptions(weak_note_floor=0.10),
    )
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "C"
    assert "Cmaj7" not in labels
    assert "B" not in dict(analysis.note_weights)


def test_playhead_note_floor_removes_weak_active_notes() -> None:
    notes = [
        _note(0.0, 1.0, 60, velocity=127),  # C
        _note(0.0, 1.0, 64, velocity=80),  # E
        _note(0.0, 1.0, 67, velocity=80),  # G
        _note(0.0, 1.0, 71, velocity=5),  # B trace
    ]

    analysis = analyze_chord_at(
        notes,
        0.5,
        scoring_options=ChordScoringOptions(weak_note_floor=0.10),
    )
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "C"
    assert "Cmaj7" not in labels
    assert "B4" not in analysis.active_note_names


def test_two_note_selection_reports_partial_harmony_hints() -> None:
    notes = [
        _note(0.0, 1.0, 55, velocity=127),  # G
        _note(0.0, 1.0, 62, velocity=127),  # D
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)

    assert analysis.label is None
    assert analysis.candidates == []
    assert analysis.note_weights == [("D", 1.0), ("G", 1.0)]
    assert "Two-note interval: G - D (perfect fifth above G)." in analysis.partial_hints
    assert "Power-chord shell: G5 (G - D)." in analysis.partial_hints
    assert any("G (add B)" in hint for hint in analysis.partial_hints)


def test_unsupported_three_note_cluster_reports_incomplete_chord_hints() -> None:
    notes = [
        _note(0.0, 1.0, 43, velocity=127),  # G
        _note(0.0, 1.0, 47, velocity=80),  # B
        _note(0.0, 1.0, 60, velocity=80),  # C
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)

    assert analysis.label is None
    assert analysis.candidates == []
    assert any("Possible incomplete chord names:" in hint for hint in analysis.partial_hints)
    assert any("Gadd4 (add D)" in hint for hint in analysis.partial_hints)


def test_weighted_selection_reports_partial_shell_candidates_from_top_notes() -> None:
    notes = [
        _note(0.0, 1.0, 44, velocity=127),  # Ab
        _note(0.0, 0.66, 53, velocity=127),  # F
        _note(0.0, 0.39, 51, velocity=127),  # Eb
        _note(0.0, 0.02, 55, velocity=127),  # trace G
        _note(0.0, 0.01, 57, velocity=127),  # trace A
    ]

    analysis = analyze_chord_region(notes, 0.0, 1.0)
    labels = [label for label, _confidence in analysis.partial_candidates]

    assert analysis.label is None
    assert analysis.candidates == []
    assert "Fm7(no5)/Ab" in labels
    assert analysis.partial_candidate_notes["Fm7(no5)/Ab"] == ["F", "Ab", "Eb"]
    assert any(
        "partial shell" in line
        for line in analysis.partial_candidate_explanations["Fm7(no5)/Ab"]
    )


def test_detect_chords_merges_adjacent_matching_regions() -> None:
    notes = [
        _note(0.0, 1.0, 60),
        _note(0.0, 1.0, 64),
        _note(0.0, 1.0, 67),
        _note(1.0, 2.0, 60),
        _note(1.0, 2.0, 64),
        _note(1.0, 2.0, 67),
    ]

    chords = detect_chords(notes)

    assert len(chords) == 1
    assert chords[0].label == "C"
    assert chords[0].start == 0.0
    assert chords[0].end == 2.0


def test_midi_note_name_formats_octaves() -> None:
    assert midi_note_name(21) == "A0"
    assert midi_note_name(60) == "C4"


def test_editor_project_reexports_shared_music_models() -> None:
    from pitchstems.editor_models import ChordRegion as SharedChordRegion
    from pitchstems.editor_models import NoteEvent as SharedNoteEvent
    from pitchstems.editor_project import ChordRegion, NoteEvent

    assert ChordRegion is SharedChordRegion
    assert NoteEvent is SharedNoteEvent


def _note(start: float, end: float, pitch: int, velocity: int = 80) -> NoteEvent:
    return NoteEvent(stem="piano", start=start, end=end, pitch=pitch, velocity=velocity)


def _write_wav(path: Path, duration_seconds: float, sample_rate: int = 8_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(duration_seconds * sample_rate)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * frame_count)
