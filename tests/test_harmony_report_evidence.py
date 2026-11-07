from types import SimpleNamespace

from pitchstems.editor_models import NoteEvent
from pitchstems.harmony_report import (
    chord_point_evidence_rows,
    chord_selection_evidence_rows,
    chord_selection_ranges_evidence_rows,
    pitch_class_list,
)


def _window() -> SimpleNamespace:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return SimpleNamespace(
        display_note_name=lambda pitch: names[pitch % 12],
        display_pitch_class_name=lambda pitch_class: names[pitch_class % 12],
    )


def _notes() -> list[NoteEvent]:
    return [
        NoteEvent("piano", 0.0, 2.0, 60, 100),
        NoteEvent("bass", 1.0, 3.0, 48, 80),
        NoteEvent("piano", 4.0, 5.0, 64, 90),
    ]


def test_selection_evidence_rows_only_cover_overlapping_notes() -> None:
    rows, totals = chord_selection_evidence_rows(_window(), _notes(), 0.0, 2.0)

    assert len(rows) == 2
    assert rows[0].startswith("bass")  # sorted by stem, then start
    assert "overlap 1.000s" in rows[0]
    assert set(totals) == {0}


def test_selection_evidence_totals_are_pitch_class_weights() -> None:
    _rows, totals = chord_selection_evidence_rows(_window(), _notes(), 0.0, 2.0)

    # C3 (48) and C4 (60) both fold into pitch class 0.
    assert set(totals) == {0}
    assert totals[0] > 0


def test_selection_evidence_rows_empty_outside_notes() -> None:
    rows, totals = chord_selection_evidence_rows(_window(), _notes(), 10.0, 11.0)

    assert rows == []
    assert totals == {}


def test_multi_range_evidence_prefixes_rows_and_sums_totals() -> None:
    single_rows, single_totals = chord_selection_evidence_rows(_window(), _notes(), 0.0, 2.0)
    rows, totals = chord_selection_ranges_evidence_rows(_window(), _notes(), [(0.0, 2.0), (0.0, 2.0)])

    assert len(rows) == 2 * len(single_rows)
    assert rows[0].startswith("range 1: ")
    assert rows[-1].startswith("range 2: ")
    assert totals[0] == 2 * single_totals[0]


def test_point_evidence_rows_list_only_sounding_notes() -> None:
    rows, totals = chord_point_evidence_rows(_window(), _notes(), 1.5)

    assert len(rows) == 2
    assert all("active at playhead" in row for row in rows)
    assert set(totals) == {0}


def test_pitch_class_list_formats_sorted_names_or_dash() -> None:
    window = _window()

    assert pitch_class_list(window, set()) == "-"
    assert pitch_class_list(window, {7, 0, 4}) == "C, E, G"
