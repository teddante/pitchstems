from __future__ import annotations

from pathlib import Path

from mido import MidiFile, MidiTrack, MetaMessage

from pitchstems.transcription import MidiResult


def combine_midi_tracks(midi_results: list[MidiResult], output_path: Path) -> Path | None:
    """Combine multiple MIDI files into one format-1 multitrack MIDI file."""
    if not midi_results:
        return None

    combined = MidiFile(type=1)
    ticks_per_beat = None

    for result in midi_results:
        source = MidiFile(result.path)
        if ticks_per_beat is None:
            ticks_per_beat = source.ticks_per_beat
            combined.ticks_per_beat = ticks_per_beat

        for index, source_track in enumerate(source.tracks):
            track = MidiTrack()
            track.append(MetaMessage("track_name", name=f"{result.stem} {index + 1}", time=0))
            track.extend(source_track)
            combined.tracks.append(track)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_path)
    return output_path

