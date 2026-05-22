from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack

from pitchstems.editor_project import (
    NoteEvent,
    active_notes_at,
    analyze_chord,
    analyze_chord_at,
    detect_chords,
    identify_chord,
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


def test_analyze_chord_includes_contextual_candidates() -> None:
    analysis = analyze_chord([60, 64, 67, 69])
    labels = [label for label, _confidence in analysis.candidates]

    assert analysis.label == "C6"
    assert "C6" in labels
    assert "Am7/C" in labels


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


def _note(start: float, end: float, pitch: int) -> NoteEvent:
    return NoteEvent(stem="piano", start=start, end=end, pitch=pitch, velocity=80)
