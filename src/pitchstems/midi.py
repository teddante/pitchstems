from __future__ import annotations

from pathlib import Path

from mido import MidiFile, MidiTrack, MetaMessage

from pitchstems.pipeline_models import MidiResult


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
            track.extend(_rescaled_messages(source_track, source.ticks_per_beat, combined.ticks_per_beat))
            combined.tracks.append(track)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_path)
    return output_path


def _rescaled_messages(source_track: MidiTrack, source_ticks: int, target_ticks: int):
    if source_ticks == target_ticks:
        return [message.copy() for message in source_track]
    scale = target_ticks / source_ticks
    source_absolute = 0
    target_absolute = 0
    messages = []
    for message in source_track:
        source_absolute += max(0, message.time)
        next_target_absolute = max(target_absolute, round(source_absolute * scale))
        messages.append(message.copy(time=next_target_absolute - target_absolute))
        target_absolute = next_target_absolute
    return messages
