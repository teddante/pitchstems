from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack

from pitchstems.editor_project import (
    NoteEvent,
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    analyze_chord_region,
    chord_tones_for_label,
    detect_chords,
    exact_chord_names_for_pitch_classes,
    identify_chord,
    midi_velocity_energy,
    midi_note_name,
    read_midi_notes,
)


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
    assert "Am7/C" in labels
    assert analysis.candidate_notes["C6"] == ["C", "E", "G", "A"]
    assert analysis.candidate_notes["Am7/C"] == ["A", "C", "E", "G"]
    assert "Am7/C" in analysis.candidate_aliases["C6"]
    assert "C6" in analysis.candidate_aliases["Am7/C"]
    assert any("Score formula:" in line for line in analysis.candidate_explanations["C6"])
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
    assert any("required-tone weight" in line for line in analysis.candidate_explanations["C"])


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
    assert "Am7/C" in labels


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


def _note(start: float, end: float, pitch: int, velocity: int = 80) -> NoteEvent:
    return NoteEvent(stem="piano", start=start, end=end, pitch=pitch, velocity=velocity)
