from types import SimpleNamespace

from pitchstems.editor_models import ChordRegion
from pitchstems.timeline_chord_geometry import (
    TimelineTrackGeometry,
    build_track_geometries,
    build_timeline_layout,
    chord_drag_mode,
    compact_chord_label,
    dragged_chord_region,
    neighbour_chords,
    snap_seconds_to_timeline_targets,
    timeline_seconds_for_x,
    timeline_x_for_seconds,
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
    assert geometries["bass"] == TimelineTrackGeometry(y=64, height=138, low_pitch=40, high_pitch=52)


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

    assert geometries["other"] == TimelineTrackGeometry(y=64, height=90, low_pitch=48, high_pitch=72)


def test_build_timeline_layout_centralizes_content_and_track_geometry() -> None:
    tracks = [SimpleNamespace(name="Bass"), SimpleNamespace(name="Piano")]

    layout = build_timeline_layout(
        tracks=tracks,
        visible_tracks={"bass", "piano"},
        pitch_ranges={"bass": (40, 52), "piano": (60, 72)},
        duration=8.0,
        pixels_per_second=100,
        label_width=72,
        ruler_height=28,
        chord_lane_height=36,
        minimum_track_height=96,
        vertical_zoom=1.0,
    )

    assert layout.chord_height == 64
    assert layout.content_width == 952
    assert layout.track_geometries["bass"].y == layout.chord_height
    assert layout.track_geometries["piano"].y == layout.chord_height + layout.track_geometries["bass"].height


def test_compact_chord_label_falls_back_to_root_name() -> None:
    assert compact_chord_label("Bb7/D") == "Bb"
    assert compact_chord_label("not-a-chord") == "no"


def test_timeline_coordinate_helpers_convert_between_seconds_and_scene_x() -> None:
    assert timeline_x_for_seconds(2.5, label_width=72, pixels_per_second=40) == 172
    assert timeline_seconds_for_x(172, label_width=72, pixels_per_second=40) == 2.5
    assert timeline_seconds_for_x(52, label_width=72, pixels_per_second=40) == 0.0
    assert timeline_seconds_for_x(
        52,
        label_width=72,
        pixels_per_second=40,
        clamp_minimum=False,
    ) == -0.5


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


def test_chord_drag_mode_detects_edges_and_body() -> None:
    chord = ChordRegion(1.0, 2.0, "C", 0.8)

    assert chord_drag_mode(seconds=1.03, chord=chord, pixels_per_second=100) == "resize_start"
    assert chord_drag_mode(seconds=1.97, chord=chord, pixels_per_second=100) == "resize_end"
    assert chord_drag_mode(seconds=1.5, chord=chord, pixels_per_second=100) == "move"


def test_neighbour_chords_ignores_dragged_chord() -> None:
    previous = ChordRegion(0.0, 1.0, "G", 0.8)
    chord = ChordRegion(1.25, 2.0, "C", 0.8)
    next_chord = ChordRegion(2.5, 3.0, "D", 0.8)

    assert neighbour_chords([previous, chord, next_chord], chord) == (previous, next_chord)


def test_dragged_chord_region_moves_within_neighbour_bounds_and_snaps() -> None:
    chord = ChordRegion(1.25, 2.0, "C", 0.8)
    previous = ChordRegion(0.0, 1.0, "G", 0.8)
    next_chord = ChordRegion(2.5, 3.0, "D", 0.8)

    dragged = dragged_chord_region(
        original=chord,
        mode="move",
        press_seconds=1.5,
        seconds=1.8,
        duration=4.0,
        previous_chord=previous,
        next_chord=next_chord,
        minimum_length=0.08,
        snap_seconds=lambda value: (1.5, 1.5 - value) if abs(value - 1.55) < 0.1 else (value, 0.0),
    )

    assert (round(dragged.start, 2), round(dragged.end, 2), dragged.label) == (1.55, 2.3, "C")


def test_dragged_chord_region_resizes_with_minimum_length() -> None:
    chord = ChordRegion(1.25, 2.0, "C", 0.8)

    dragged = dragged_chord_region(
        original=chord,
        mode="resize_end",
        press_seconds=1.5,
        seconds=1.26,
        duration=4.0,
        previous_chord=None,
        next_chord=None,
        minimum_length=0.2,
        snap_seconds=lambda value: (value, 0.0),
        snap_enabled=False,
    )

    assert dragged == ChordRegion(1.25, 1.45, "C", 0.8)
