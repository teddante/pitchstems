from pitchstems.chord_scoring import (
    partial_chord_completions,
    partial_shell_candidates_from_weights,
    perfect_fifth_root,
)


def test_partial_shell_needs_three_weighted_pitch_classes() -> None:
    assert partial_shell_candidates_from_weights({0: 1.0, 4: 1.0}) == []


def test_partial_shell_rejects_required_tones_that_are_excluded() -> None:
    weights = {0: 1.0, 4: 0.9, 7: 0.8, 11: 0.1}

    assert partial_shell_candidates_from_weights(weights, excluded_pitch_classes={0, 4, 7}) == []


def test_partial_shell_keeps_required_tones_in_every_candidate() -> None:
    weights = {0: 1.0, 4: 0.9, 7: 0.8, 9: 0.05}

    candidates = partial_shell_candidates_from_weights(weights, required_pitch_classes={9})

    assert all(9 in candidate.observed_tones for candidate in candidates)


def test_perfect_fifth_root_prefers_the_preferred_root_then_any_fifth() -> None:
    assert perfect_fifth_root({0, 7}, 0) == 0
    assert perfect_fifth_root({0, 7}, 7) == 0
    assert perfect_fifth_root({0, 1}, 0) is None
    assert perfect_fifth_root({0, 7, 2}, 0) is None


def test_partial_completions_respect_observed_and_excluded_tones() -> None:
    completions = partial_chord_completions({0, 4}, excluded_pitch_classes={10})

    assert completions
    assert "C7" not in completions
    assert "Cm7" not in completions
