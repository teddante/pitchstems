from __future__ import annotations

from dataclasses import dataclass


TRACK_CONTROL_MIN_HEIGHT = 96


@dataclass(frozen=True)
class TrackControlVisibility:
    toggles: bool
    audio_volume: bool
    midi_volume: bool


def track_control_panel_height(timeline_track_height: float | int | None) -> int:
    if timeline_track_height is None:
        return TRACK_CONTROL_MIN_HEIGHT
    return max(TRACK_CONTROL_MIN_HEIGHT, int(round(timeline_track_height)))


def track_control_visibility(height: float | int) -> TrackControlVisibility:
    """Keep the normal zoomed-out lane height large enough to show all controls."""
    compact_limit = TRACK_CONTROL_MIN_HEIGHT
    return TrackControlVisibility(
        toggles=height >= 38,
        audio_volume=height >= compact_limit,
        midi_volume=height >= compact_limit,
    )
