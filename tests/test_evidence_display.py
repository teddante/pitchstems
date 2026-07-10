from dataclasses import dataclass

from pitchstems.evidence_display import percent_text, visible_scale_candidates


@dataclass(frozen=True)
class _Scale:
    name: str


@dataclass(frozen=True)
class _Candidate:
    scale: _Scale


def test_percent_text_clamps_without_ascii_bar() -> None:
    assert percent_text(0.64) == "64%"
    assert percent_text(2.0) == "100%"


def test_visible_scale_candidates_can_hide_chromatic_candidates() -> None:
    chromatic = _Candidate(_Scale("Chromatic"))
    major = _Candidate(_Scale("Ionian"))

    assert visible_scale_candidates([chromatic, major], show_chromatic=False) == [major]
    assert visible_scale_candidates([chromatic, major], show_chromatic=True) == [chromatic, major]
