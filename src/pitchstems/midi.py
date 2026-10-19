from __future__ import annotations

from pathlib import Path

from typing import Any, Iterable

from mido import MidiFile, MidiTrack, MetaMessage

from pitchstems.pipeline_models import MidiResult


CONDUCTOR_META_TYPES = {"set_tempo", "time_signature", "key_signature"}
DRUM_CHANNEL = 9
MELODIC_CHANNELS = tuple(channel for channel in range(16) if channel != DRUM_CHANNEL)
PERCUSSIVE_STEM_NAMES = {"drums", "drum", "percussion"}


def combine_midi_tracks(midi_results: list[MidiResult], output_path: Path) -> Path | None:
    """Combine multiple MIDI files into one format-1 multitrack MIDI file.

    Each stem gets its own MIDI channel (drums use General MIDI channel 10), so a
    plain GM player does not play every stem with one shared instrument. Tempo,
    time- and key-signature events are collected once into a leading conductor
    track instead of being repeated in every stem track.
    """
    if not midi_results:
        return None

    combined = MidiFile(type=1)
    ticks_per_beat: int | None = None
    conductor: list[tuple[int, Any]] = []
    stem_tracks: list[MidiTrack] = []
    melodic_index = 0

    for result in midi_results:
        source = MidiFile(result.path)
        if ticks_per_beat is None:
            ticks_per_beat = source.ticks_per_beat
            combined.ticks_per_beat = ticks_per_beat
        if result.stem.lower() in PERCUSSIVE_STEM_NAMES:
            channel = DRUM_CHANNEL
        else:
            channel = MELODIC_CHANNELS[melodic_index % len(MELODIC_CHANNELS)]
            melodic_index += 1
        take_conductor = not conductor

        for index, source_track in enumerate(source.tracks):
            timed = _absolute_messages(
                _rescaled_messages(source_track, source.ticks_per_beat, combined.ticks_per_beat)
            )
            kept: list[tuple[int, Any]] = []
            for tick, message in timed:
                if message.is_meta and message.type in CONDUCTOR_META_TYPES:
                    if take_conductor:
                        conductor.append((tick, message))
                    continue
                if message.is_meta and message.type in {"track_name", "end_of_track"}:
                    continue
                if hasattr(message, "channel"):
                    message = message.copy(channel=channel)
                kept.append((tick, message))
            if not any(not message.is_meta for _tick, message in kept):
                continue
            track = MidiTrack()
            track.append(MetaMessage("track_name", name=f"{result.stem} {index + 1}", time=0))
            track.extend(_relative_messages(kept))
            stem_tracks.append(track)

    if conductor:
        conductor_track = MidiTrack()
        conductor_track.append(MetaMessage("track_name", name="Tempo", time=0))
        conductor_track.extend(_relative_messages(sorted(conductor, key=lambda item: item[0])))
        combined.tracks.append(conductor_track)
    combined.tracks.extend(stem_tracks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(output_path)
    return output_path


def _absolute_messages(messages: Iterable[Any]) -> list[tuple[int, Any]]:
    tick = 0
    timed: list[tuple[int, Any]] = []
    for message in messages:
        tick += message.time
        timed.append((tick, message))
    return timed


def _relative_messages(timed: Iterable[tuple[int, Any]]) -> list[Any]:
    previous = 0
    messages = []
    for tick, message in timed:
        messages.append(message.copy(time=tick - previous))
        previous = tick
    return messages


def _rescaled_messages(source_track: MidiTrack, source_ticks: int, target_ticks: int) -> list[Any]:
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
