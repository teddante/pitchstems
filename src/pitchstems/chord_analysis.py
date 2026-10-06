from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from pitchstems.chord_explanation import partial_harmony_hints
from pitchstems.chord_naming import (
    PITCH_NAMES,
    alternate_chord_names_for_label,
    chord_tones_for_label,
)
from pitchstems.chord_scoring import (
    ChordScoringOptions,
    PartialChordCandidate,
    _candidate_labels,
    _partial_shell_candidates_from_weights,
    _score_root,
    _score_weighted_root_candidates,
)
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.midi_energy import point_pitch_energy, ranges_pitch_energy, region_pitch_energy
from pitchstems.notation import midi_note_name, normalized_pitch_class_weights

PLAIN_CHORD_THRESHOLD = 0.70
WEIGHTED_CHORD_THRESHOLD = 0.30
PLAIN_CANDIDATE_MARGIN = 0.18
WEIGHTED_CANDIDATE_MARGIN = 0.22
MIN_WEIGHTED_TONE_SUPPORT = 0.005
PARTIAL_HINT_LIMIT = 6


@dataclass(frozen=True)
class ChordAnalysis:
    label: str | None
    confidence: float
    active_note_names: list[str]
    pitch_classes: list[int]
    root: int | None = None
    bass: int | None = None
    candidates: list[tuple[str, float]] = field(default_factory=list)
    candidate_notes: dict[str, list[str]] = field(default_factory=dict)
    candidate_aliases: dict[str, list[str]] = field(default_factory=dict)
    candidate_explanations: dict[str, list[str]] = field(default_factory=dict)
    note_weights: list[tuple[str, float]] = field(default_factory=list)
    partial_hints: list[str] = field(default_factory=list)
    partial_candidates: list[tuple[str, float]] = field(default_factory=list)
    partial_candidate_notes: dict[str, list[str]] = field(default_factory=dict)
    partial_candidate_aliases: dict[str, list[str]] = field(default_factory=dict)
    partial_candidate_explanations: dict[str, list[str]] = field(default_factory=dict)


def detect_chords(notes: list[NoteEvent], minimum_region: float = 0.18) -> list[ChordRegion]:
    """Infer coarse chord regions from simultaneous MIDI notes."""
    if not notes:
        return []

    starts: dict[float, list[NoteEvent]] = {}
    ends: dict[float, list[NoteEvent]] = {}
    for note in notes:
        starts.setdefault(round(note.start, 6), []).append(note)
        ends.setdefault(round(note.end, 6), []).append(note)
    times = sorted(set(starts) | set(ends))
    atomic_regions: list[ChordRegion] = []
    active: list[NoteEvent] = []
    analysis_cache: dict[tuple[int, ...], ChordAnalysis] = {}
    for start, end in pairwise(times):
        for note in ends.get(start, []):
            with contextlib.suppress(ValueError):
                active.remove(note)
        active.extend(starts.get(start, []))
        pitches = tuple(sorted(note.pitch for note in active))
        analysis = analysis_cache.get(pitches)
        if analysis is None:
            analysis = analyze_chord(list(pitches))
            analysis_cache[pitches] = analysis
        if not analysis.label:
            continue
        if (
            atomic_regions
            and atomic_regions[-1].label == analysis.label
            and abs(atomic_regions[-1].end - start) < 0.05
        ):
            previous = atomic_regions[-1]
            atomic_regions[-1] = ChordRegion(
                start=previous.start,
                end=end,
                label=previous.label,
                confidence=max(previous.confidence, analysis.confidence),
            )
        else:
            atomic_regions.append(
                ChordRegion(
                    start=start,
                    end=end,
                    label=analysis.label,
                    confidence=analysis.confidence,
                )
            )
    return [region for region in atomic_regions if region.duration >= minimum_region]


def analyze_chord_at(
    notes: list[NoteEvent],
    seconds: float,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    pitch_weights, exact_pitch_weights = point_pitch_energy(notes, seconds)
    return _analyze_pitch_weights(
        pitch_weights,
        exact_pitch_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
        scoring_options=scoring_options,
    )


def analyze_chord_region(
    notes: list[NoteEvent],
    start: float,
    end: float,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    start, end = sorted((start, end))
    if end - start <= 0:
        return ChordAnalysis(None, 0.0, [], [])
    pitch_weights, exact_pitch_weights = region_pitch_energy(notes, start, end)
    return _analyze_pitch_weights(
        pitch_weights,
        exact_pitch_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
        scoring_options=scoring_options,
    )


def analyze_chord_regions(
    notes: list[NoteEvent],
    ranges: list[tuple[float, float]],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    pitch_weights, exact_pitch_weights = ranges_pitch_energy(notes, ranges)
    if not pitch_weights and not exact_pitch_weights:
        return ChordAnalysis(None, 0.0, [], [])
    return _analyze_pitch_weights(
        pitch_weights,
        exact_pitch_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
        scoring_options=scoring_options,
    )


def _analyze_pitch_weights(
    pitch_weights: dict[int, float],
    exact_pitch_weights: dict[int, float],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    options = scoring_options or ChordScoringOptions()
    if pitch_weights and options.weak_note_floor > 0:
        pitch_weights, exact_pitch_weights = _drop_weak_notes(
            pitch_weights,
            exact_pitch_weights,
            options.weak_note_floor,
            required_pitch_classes,
        )

    active_note_names = [midi_note_name(pitch) for pitch in sorted(exact_pitch_weights)]
    if not pitch_weights:
        return ChordAnalysis(None, 0.0, active_note_names, [])
    max_exact_weight = max(exact_pitch_weights.values())
    bass = min(
        pitch
        for pitch, weight in exact_pitch_weights.items()
        if weight >= max_exact_weight * 0.12
    ) % 12
    note_weights = normalized_pitch_class_weights(pitch_weights)
    effective_pitch_classes = set(pitch_weights)
    if required_pitch_classes:
        effective_pitch_classes |= required_pitch_classes
    if len(effective_pitch_classes) < 3:
        return _unresolved(
            active_note_names,
            sorted(pitch_weights),
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
            note_weights=note_weights,
        )
    return _analyze_weighted_pitch_classes(
        pitch_weights,
        bass,
        active_note_names,
        note_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
    )


def _drop_weak_notes(
    pitch_weights: dict[int, float],
    exact_pitch_weights: dict[int, float],
    weak_note_floor: float,
    required_pitch_classes: set[int] | None,
) -> tuple[dict[int, float], dict[int, float]]:
    floor = max(pitch_weights.values()) * weak_note_floor
    kept = {pitch_class for pitch_class, weight in pitch_weights.items() if weight >= floor}
    if required_pitch_classes:
        kept |= required_pitch_classes
    return (
        {pitch_class: weight for pitch_class, weight in pitch_weights.items() if pitch_class in kept},
        {pitch: weight for pitch, weight in exact_pitch_weights.items() if pitch % 12 in kept},
    )


def analyze_chord(
    pitches: list[int],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    del scoring_options
    active_note_names = [midi_note_name(pitch) for pitch in sorted(set(pitches))]
    observed_pitch_classes = {pitch % 12 for pitch in pitches}
    effective_pitch_classes = set(observed_pitch_classes)
    if required_pitch_classes:
        effective_pitch_classes |= required_pitch_classes
    pitch_classes = sorted(effective_pitch_classes)
    if len(effective_pitch_classes) < 3:
        return _unresolved(
            active_note_names,
            sorted(observed_pitch_classes),
            min(pitches) % 12 if pitches else None,
            required_pitch_classes,
            excluded_pitch_classes,
        )

    bass = min(pitches) % 12 if pitches else min(effective_pitch_classes)
    scored_roots: list[tuple[str, float, int, list[str], tuple[float, ...]]] = []
    for root in range(12):
        scored = _score_root(
            root,
            effective_pitch_classes,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        )
        if scored is not None:
            label, score, explanation, rank_key = scored
            scored_roots.append((label, score, root, explanation, rank_key))
    if not scored_roots:
        return _unresolved(
            active_note_names,
            pitch_classes,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        )

    scored_roots.sort(key=lambda item: item[4], reverse=True)
    best_label, best_score, best_root, _best_explanation, _best_rank_key = scored_roots[0]
    if best_label is None or best_score < PLAIN_CHORD_THRESHOLD:
        return _unresolved(
            active_note_names,
            pitch_classes,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
            confidence=best_score,
            root=best_root,
        )
    candidates = _candidate_labels(
        scored_roots,
        threshold=PLAIN_CHORD_THRESHOLD,
        margin=PLAIN_CANDIDATE_MARGIN,
        best_score=best_score,
        pitch_classes=set(pitch_classes),
    )
    explanations = {
        (label, score): explanation for label, score, _root, explanation, _key in scored_roots
    }
    return ChordAnalysis(
        best_label,
        best_score,
        active_note_names,
        pitch_classes,
        best_root,
        bass,
        **_candidate_fields(candidates, explanations, bass),
    )


def _analyze_weighted_pitch_classes(
    pitch_weights: dict[int, float],
    bass: int,
    active_note_names: list[str],
    note_weights: list[tuple[str, float]],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> ChordAnalysis:
    pitch_classes = sorted(pitch_weights)
    scored_roots = []
    for root in range(12):
        for label, score, explanation, rank_key in _score_weighted_root_candidates(
            root,
            pitch_weights,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        ):
            scored_roots.append((label, score, explanation, root, rank_key))
    if not scored_roots:
        return _unresolved(
            active_note_names,
            pitch_classes,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
            note_weights=note_weights,
            partial_weights=pitch_weights,
        )
    scored_roots.sort(key=lambda item: item[4], reverse=True)
    best_label, best_score, _best_explanation, best_root, _best_rank_key = scored_roots[0]
    candidates = _candidate_labels(
        scored_roots,
        threshold=WEIGHTED_CHORD_THRESHOLD,
        margin=WEIGHTED_CANDIDATE_MARGIN,
        best_score=best_score,
        pitch_classes=set(pitch_classes),
    )
    explanations = {
        (label, score): explanation for label, score, explanation, _root, _key in scored_roots
    }
    candidate_fields = _candidate_fields(candidates, explanations, bass)
    if best_score < WEIGHTED_CHORD_THRESHOLD:
        return _unresolved(
            active_note_names,
            pitch_classes,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
            confidence=best_score,
            root=best_root,
            note_weights=note_weights,
            partial_weights=pitch_weights,
            **candidate_fields,
        )
    return ChordAnalysis(
        best_label,
        best_score,
        active_note_names,
        pitch_classes,
        best_root,
        bass,
        note_weights=note_weights,
        **candidate_fields,
    )


def _candidate_fields(
    candidates: list[tuple[str, float]],
    explanations: dict[tuple[str, float], list[str]],
    bass: int,
) -> dict[str, Any]:
    return {
        "candidates": candidates,
        "candidate_notes": {label: chord_tones_for_label(label) for label, _score in candidates},
        "candidate_aliases": {
            label: alternate_chord_names_for_label(label, bass) for label, _score in candidates
        },
        "candidate_explanations": {
            label: explanations[(label, score)]
            for label, score in candidates
            if (label, score) in explanations
        },
    }


def _unresolved(
    active_note_names: list[str],
    pitch_classes: list[int],
    bass: int | None,
    required_pitch_classes: set[int] | None,
    excluded_pitch_classes: set[int] | None,
    *,
    confidence: float = 0.0,
    root: int | None = None,
    note_weights: list[tuple[str, float]] | None = None,
    partial_weights: dict[int, float] | None = None,
    **candidate_fields: Any,
) -> ChordAnalysis:
    """Build a no-label analysis that still carries partial-harmony hints."""
    partial: list[PartialChordCandidate] = []
    if partial_weights is not None and bass is not None:
        partial = _partial_shell_candidates_from_weights(
            partial_weights,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        )
    return ChordAnalysis(
        None,
        confidence,
        active_note_names,
        pitch_classes,
        root,
        bass,
        note_weights=note_weights or [],
        partial_hints=partial_harmony_hints(
            set(pitch_classes),
            bass,
            required_pitch_classes=required_pitch_classes,
            excluded_pitch_classes=excluded_pitch_classes,
        ),
        partial_candidates=[(candidate.label, candidate.score) for candidate in partial],
        partial_candidate_notes={
            candidate.label: [PITCH_NAMES[pitch_class] for pitch_class in candidate.observed_tones]
            for candidate in partial
        },
        partial_candidate_aliases={candidate.label: [] for candidate in partial},
        partial_candidate_explanations={
            candidate.label: candidate.explanation for candidate in partial
        },
        **candidate_fields,
    )
