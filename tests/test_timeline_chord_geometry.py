from types import SimpleNamespace

from pitchstems.editor_models import ChordRegion
from pitchstems.timeline_chord_geometry import (
    build_track_geometries,
    compact_chord_label,
    snap_seconds_to_timeline_targets,
)


def test_build_track_geometries_uses_visible_tracks_and_pitch_ranges() -> None:
    tracks = [SimpleNamespace(name="Bass"), SimpleNamespace(name="Piano")]

    geometries = build_track_geometries(
        tracks=tracks,
        visible_tracks={"bass"},
        pitch_ranges={"bass": (40, 52)},
        chord_height=64,
        minimum_track_height=72,
        vertical_zoom=1.0,
    )

    assert set(geometries) == {"bass"}
    assert geometries["bass"] == (64, 138, 40, 52)


def test_build_track_geometries_uses_default_pitch_range_for_empty_tracks() -> None:
    tracks = [SimpleNamespace(name="Other")]

    geometries = build_track_geometries(
        tracks=tracks,
        visible_tracks={"other"},
        pitch_ranges={},
        chord_height=64,
        minimum_track_height=90,
        vertical_zoom=0.5,
    )

    assert geometries["other"] == (64, 90, 48, 72)


def test_compact_chord_label_falls_back_to_root_name() -> None:
    assert compact_chord_label("Bb7/D") == "Bb"
    assert compact_chord_label("not-a-chord") == "no"


def test_snap_seconds_to_timeline_targets_prefers_nearby_target() -> None:
    ignored = ChordRegion(1.0, 2.0, "C", 0.8)
    nearby = ChordRegion(2.5, 3.25, "G", 0.8)

    snapped, delta = snap_seconds_to_timeline_targets(
        seconds=2.47,
        duration=4.0,
        position=1.5,
        selection_start=0.75,
        selection_end=3.5,
        chords=[ignored, nearby],
        ignored_chord=ignored,
        pixels_per_second=100,
    )

    assert snapped == 2.5
    assert round(delta, 2) == 0.03
    assert snap_seconds_to_timeline_targets(
        seconds=2.35,
        duration=4.0,
        position=1.5,
        selection_start=0.75,
        selection_end=3.5,
        chords=[ignored, nearby],
        ignored_chord=ignored,
        pixels_per_second=100,
    ) == (2.35, 0.0)
