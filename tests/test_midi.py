from pathlib import Path

from mido import Message, MidiFile, MidiTrack

from pitchstems.midi import combine_midi_tracks
from pitchstems.transcription import MidiResult


def _write_midi(path: Path, note: int) -> None:
    midi = MidiFile()
    track = MidiTrack()
    track.append(Message("note_on", note=note, velocity=64, time=0))
    track.append(Message("note_off", note=note, velocity=0, time=120))
    midi.tracks.append(track)
    midi.save(path)


def test_combine_midi_tracks_creates_multitrack_file(tmp_path: Path) -> None:
    vocal = tmp_path / "vocals.mid"
    bass = tmp_path / "bass.mid"
    _write_midi(vocal, 60)
    _write_midi(bass, 40)

    output = tmp_path / "combined.mid"
    result = combine_midi_tracks(
        [MidiResult("vocals", vocal), MidiResult("bass", bass)],
        output,
    )

    assert result == output
    combined = MidiFile(output)
    assert combined.type == 1
    assert len(combined.tracks) == 2
