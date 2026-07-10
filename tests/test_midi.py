from pathlib import Path

from mido import Message, MidiFile, MidiTrack

from pitchstems.midi import _rescaled_messages, combine_midi_tracks
from pitchstems.pipeline_models import MidiResult


def _write_midi(path: Path, note: int, ticks_per_beat: int = 480, note_off_ticks: int = 120) -> None:
    midi = MidiFile(ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    track.append(Message("note_on", note=note, velocity=64, time=0))
    track.append(Message("note_off", note=note, velocity=0, time=note_off_ticks))
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


def test_combine_midi_tracks_rescales_different_ticks_per_beat(tmp_path: Path) -> None:
    first = tmp_path / "first.mid"
    second = tmp_path / "second.mid"
    _write_midi(first, 60, ticks_per_beat=480, note_off_ticks=480)
    _write_midi(second, 64, ticks_per_beat=960, note_off_ticks=960)

    output = tmp_path / "combined.mid"
    combine_midi_tracks(
        [MidiResult("first", first), MidiResult("second", second)],
        output,
    )

    combined = MidiFile(output)
    assert combined.ticks_per_beat == 480
    assert combined.tracks[1][2].time == 480


def test_rescaled_messages_preserve_cumulative_fractional_ticks() -> None:
    track = MidiTrack(
        [
            Message("note_on", note=60, velocity=64, time=1),
            Message("note_off", note=60, velocity=0, time=1),
        ]
    )

    result = _rescaled_messages(track, source_ticks=960, target_ticks=480)

    assert sum(message.time for message in result) == 1
