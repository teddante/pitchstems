from pitchstems.notation import pitch_class_name
from pitchstems.scale_analysis import ScaleCandidate, ScaleDefinition
from pitchstems.theory_display import (
    display_scale_candidate_label,
    display_scale_candidate_notes,
    display_theory_note_names,
)


def _candidate(root: int = 1) -> ScaleCandidate:
    return ScaleCandidate(
        label="Db major",
        root=root,
        scale=ScaleDefinition("Ionian", (0, 2, 4, 5, 7, 9, 11), "major"),
        notes=[],
        score=1.0,
        pitch_fit=1.0,
        outside_energy=0.0,
        center_strength=1.0,
        chord_support=1.0,
    )


def test_display_scale_candidate_respects_explicit_notation_preference() -> None:
    candidate = _candidate()

    assert display_scale_candidate_label(candidate, "sharp") == "C# major"
    assert display_scale_candidate_notes(candidate, "sharp") == ["C#", "D#", "E#", "F#", "G#", "A#", "B#"]
    assert display_scale_candidate_label(candidate, "flat") == "Db major"
    assert display_scale_candidate_notes(candidate, "flat") == ["Db", "Eb", "F", "Gb", "Ab", "Bb", "C"]


def test_display_theory_note_names_uses_formatter_for_known_notes() -> None:
    assert display_theory_note_names(
        ["Bb", "C#", "noise"],
        lambda pitch_class: pitch_class_name(pitch_class, "sharp"),
    ) == ["A#", "C#", "noise"]
