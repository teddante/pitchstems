"""Compatibility exports for chord scoring internals.

The implementation still lives in ``pitchstems.chord_analysis`` so public imports
can stabilize before a larger mechanical extraction. Do not add new scoring logic
here; move the implementation from ``chord_analysis`` first.
"""

from __future__ import annotations

from pitchstems.chord_analysis import (
    ChordScoringOptions,
    PartialChordCandidate,
    _label_matches_constraints,
    _normalized_note_weights,
    _partial_chord_completions,
    _partial_quality_priority,
    _partial_shell_candidates_from_weights,
    _plain_score_explanation,
    _score_root,
    _score_weighted_root_candidates,
    _weighted_score_explanation,
)

__all__ = [
    "ChordScoringOptions",
    "PartialChordCandidate",
    "_label_matches_constraints",
    "_normalized_note_weights",
    "_partial_chord_completions",
    "_partial_quality_priority",
    "_partial_shell_candidates_from_weights",
    "_plain_score_explanation",
    "_score_root",
    "_score_weighted_root_candidates",
    "_weighted_score_explanation",
]
