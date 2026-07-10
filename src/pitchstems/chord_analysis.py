from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from itertools import pairwise

from pitchstems.chord_naming import (
    PITCH_NAMES,
    alternate_chord_names_for_label,
    chord_bass_name_for_label,
    chord_pitch_classes_for_label,
    chord_sounding_pitch_classes_for_label,
    chord_tones_for_label,
    display_chord_label,
    exact_chord_names_for_pitch_classes,
)
from pitchstems.chord_explanation import partial_harmony_hints
from pitchstems.chord_scoring import (
    ChordScoringOptions,
    PartialChordCandidate,
    _candidate_labels,
    _normalized_note_weights,
    _partial_shell_candidates_from_weights,
    _score_root,
    _score_weighted_root_candidates,
)
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.midi_energy import (
    active_notes_at as energy_active_notes_at,
    midi_velocity_energy as energy_midi_velocity_energy,
    point_pitch_energy,
    region_pitch_energy,
)
from pitchstems.notation import (
    midi_note_name as spell_midi_note_name,
)

__all__ = [
    "ChordAnalysis",
    "ChordRegion",
    "ChordScoringOptions",
    "PITCH_NAMES",
    "PartialChordCandidate",
    "active_notes_at",
    "alternate_chord_names_for_label",
    "analyze_chord",
    "analyze_chord_at",
    "analyze_chord_region",
    "analyze_chord_regions",
    "chord_bass_name_for_label",
    "chord_pitch_classes_for_label",
    "chord_sounding_pitch_classes_for_label",
    "chord_tones_for_label",
    "detect_chords",
    "display_chord_label",
    "exact_chord_names_for_pitch_classes",
    "identify_chord",
    "midi_note_name",
    "midi_velocity_energy",
    "partial_harmony_hints",
]

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


def active_notes_at(notes: list[NoteEvent], seconds: float) -> list[NoteEvent]:
    return energy_active_notes_at(notes, seconds)


def midi_velocity_energy(velocity: int) -> float:
    return energy_midi_velocity_energy(velocity)


def analyze_chord_at(
    notes: list[NoteEvent],
    seconds: float,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    options = scoring_options or ChordScoringOptions()
    pitch_weights, exact_pitch_weights = point_pitch_energy(notes, seconds)

    if pitch_weights and options.weak_note_floor > 0:
        max_weight = max(pitch_weights.values())
        kept_pitch_classes = {
            pitch_class
            for pitch_class, weight in pitch_weights.items()
            if weight >= max_weight * options.weak_note_floor
        }
        if required_pitch_classes:
            kept_pitch_classes |= required_pitch_classes
        pitch_weights = {
            pitch_class: weight
            for pitch_class, weight in pitch_weights.items()
            if pitch_class in kept_pitch_classes
        }
        exact_pitch_weights = {
            pitch: weight
            for pitch, weight in exact_pitch_weights.items()
            if pitch % 12 in kept_pitch_classes
        }

    active_note_names = [midi_note_name(pitch) for pitch in sorted(exact_pitch_weights)]
    if not pitch_weights:
        return ChordAnalysis(None, 0.0, active_note_names, [])

    max_exact_weight = max(exact_pitch_weights.values())
    bass_pitch = min(
        pitch
        for pitch, weight in exact_pitch_weights.items()
        if weight >= max_exact_weight * 0.12
    )
    note_weights = _normalized_note_weights(pitch_weights)
    effective_pitch_classes = set(pitch_weights)
    if required_pitch_classes:
        effective_pitch_classes |= required_pitch_classes
    if len(effective_pitch_classes) < 3:
        return ChordAnalysis(
            None,
            0.0,
            active_note_names,
            sorted(pitch_weights),
            bass=bass_pitch % 12,
            note_weights=note_weights,
            partial_hints=partial_harmony_hints(
                set(pitch_weights),
                bass_pitch % 12,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
        )
    return _analyze_weighted_pitch_classes(
        pitch_weights,
        bass_pitch % 12,
        active_note_names,
        note_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
    )


def analyze_chord_region(
    notes: list[NoteEvent],
    start: float,
    end: float,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    options = scoring_options or ChordScoringOptions()
    start, end = sorted((start, end))
    if end - start <= 0:
        return ChordAnalysis(None, 0.0, [], [])

    pitch_weights, exact_pitch_weights = region_pitch_energy(notes, start, end)
    return _analyze_region_pitch_weights(
        pitch_weights,
        exact_pitch_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
        scoring_options=options,
    )


def analyze_chord_regions(
    notes: list[NoteEvent],
    ranges: list[tuple[float, float]],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    options = scoring_options or ChordScoringOptions()
    pitch_weights: dict[int, float] = {}
    exact_pitch_weights: dict[int, float] = {}
    for start, end in ranges:
        start, end = sorted((start, end))
        if end - start <= 0:
            continue
        region_weights, region_exact_weights = region_pitch_energy(notes, start, end)
        for pitch_class, weight in region_weights.items():
            pitch_weights[pitch_class] = pitch_weights.get(pitch_class, 0.0) + weight
        for pitch, weight in region_exact_weights.items():
            exact_pitch_weights[pitch] = exact_pitch_weights.get(pitch, 0.0) + weight
    if not pitch_weights and not exact_pitch_weights:
        return ChordAnalysis(None, 0.0, [], [])
    return _analyze_region_pitch_weights(
        pitch_weights,
        exact_pitch_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
        scoring_options=options,
    )


def _analyze_region_pitch_weights(
    pitch_weights: dict[int, float],
    exact_pitch_weights: dict[int, float],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordAnalysis:
    options = scoring_options or ChordScoringOptions()
    if pitch_weights and options.weak_note_floor > 0:
        max_pitch_class_weight = max(pitch_weights.values())
        kept_pitch_classes = {
            pitch_class
            for pitch_class, weight in pitch_weights.items()
            if weight >= max_pitch_class_weight * options.weak_note_floor
        }
        if required_pitch_classes:
            kept_pitch_classes |= required_pitch_classes
        pitch_weights = {
            pitch_class: weight
            for pitch_class, weight in pitch_weights.items()
            if pitch_class in kept_pitch_classes
        }
        exact_pitch_weights = {
            pitch: weight
            for pitch, weight in exact_pitch_weights.items()
            if pitch % 12 in kept_pitch_classes
        }

    active_note_names = [midi_note_name(pitch) for pitch in sorted(exact_pitch_weights)]
    if not pitch_weights:
        return ChordAnalysis(None, 0.0, active_note_names, sorted(pitch_weights))
    max_exact_weight = max(exact_pitch_weights.values())
    bass_pitch = min(
        pitch
        for pitch, weight in exact_pitch_weights.items()
        if weight >= max_exact_weight * 0.12
    )
    note_weights = _normalized_note_weights(pitch_weights)
    effective_pitch_classes = set(pitch_weights)
    if required_pitch_classes:
        effective_pitch_classes |= required_pitch_classes
    if len(effective_pitch_classes) < 3:
        return ChordAnalysis(
            None,
            0.0,
            active_note_names,
            sorted(pitch_weights),
            bass=bass_pitch % 12,
            note_weights=note_weights,
            partial_hints=partial_harmony_hints(
                set(pitch_weights),
                bass_pitch % 12,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
        )
    return _analyze_weighted_pitch_classes(
        pitch_weights,
        bass_pitch % 12,
        active_note_names,
        note_weights,
        required_pitch_classes=required_pitch_classes,
        excluded_pitch_classes=excluded_pitch_classes,
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
        bass = min(pitches) % 12 if pitches else None
        return ChordAnalysis(
            None,
            0.0,
            active_note_names,
            sorted(observed_pitch_classes),
            bass=bass,
            partial_hints=partial_harmony_hints(
                set(observed_pitch_classes),
                bass,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
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
        return ChordAnalysis(
            None,
            0.0,
            active_note_names,
            pitch_classes,
            bass=bass,
            partial_hints=partial_harmony_hints(
                set(pitch_classes),
                bass,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
        )

    scored_roots.sort(key=lambda item: item[4], reverse=True)
    best_label, best_score, best_root, _best_explanation, _best_rank_key = scored_roots[0]
    candidates = _candidate_labels(
        scored_roots,
        threshold=PLAIN_CHORD_THRESHOLD,
        margin=PLAIN_CANDIDATE_MARGIN,
        best_score=best_score,
        pitch_classes=set(pitch_classes),
    )
    candidate_notes = {
        label: chord_tones_for_label(label)
        for label, _score in candidates
    }
    candidate_aliases = {
        label: alternate_chord_names_for_label(label, bass)
        for label, _score in candidates
    }
    candidate_explanations = {
        label: explanation
        for label, score, _root, explanation, _rank_key in scored_roots
        if (label, score) in candidates
    }

    if best_label is None or best_score < PLAIN_CHORD_THRESHOLD:
        return ChordAnalysis(
            None,
            best_score,
            active_note_names,
            pitch_classes,
            best_root,
            bass,
            partial_hints=partial_harmony_hints(
                set(pitch_classes),
                bass,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
        )
    return ChordAnalysis(
        best_label,
        best_score,
        active_note_names,
        pitch_classes,
        best_root,
        bass,
        candidates,
        candidate_notes,
        candidate_aliases,
        candidate_explanations,
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
        partial_candidates = _partial_shell_candidates_from_weights(
            pitch_weights,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        )
        return ChordAnalysis(
            None,
            0.0,
            active_note_names,
            pitch_classes,
            bass=bass,
            note_weights=note_weights,
            partial_hints=partial_harmony_hints(
                set(pitch_classes),
                bass,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
            partial_candidates=[(candidate.label, candidate.score) for candidate in partial_candidates],
            partial_candidate_notes={
                candidate.label: [PITCH_NAMES[pitch_class] for pitch_class in candidate.observed_tones]
                for candidate in partial_candidates
            },
            partial_candidate_aliases={
                candidate.label: []
                for candidate in partial_candidates
            },
            partial_candidate_explanations={
                candidate.label: candidate.explanation
                for candidate in partial_candidates
            },
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
    candidate_notes = {
        label: chord_tones_for_label(label)
        for label, _score in candidates
    }
    candidate_aliases = {
        label: alternate_chord_names_for_label(label, bass)
        for label, _score in candidates
    }
    candidate_explanations = {
        label: explanation
        for label, score, explanation, _root, _rank_key in scored_roots
        if (label, score) in candidates
    }
    if best_score < WEIGHTED_CHORD_THRESHOLD:
        partial_candidates = _partial_shell_candidates_from_weights(
            pitch_weights,
            bass,
            required_pitch_classes,
            excluded_pitch_classes,
        )
        return ChordAnalysis(
            None,
            best_score,
            active_note_names,
            pitch_classes,
            best_root,
            bass,
            candidates,
            candidate_notes,
            candidate_aliases,
            candidate_explanations,
            note_weights,
            partial_harmony_hints(
                set(pitch_classes),
                bass,
                required_pitch_classes=required_pitch_classes,
                excluded_pitch_classes=excluded_pitch_classes,
            ),
            [(candidate.label, candidate.score) for candidate in partial_candidates],
            {
                candidate.label: [PITCH_NAMES[pitch_class] for pitch_class in candidate.observed_tones]
                for candidate in partial_candidates
            },
            {
                candidate.label: []
                for candidate in partial_candidates
            },
            {
                candidate.label: candidate.explanation
                for candidate in partial_candidates
            },
        )
    return ChordAnalysis(
        best_label,
        best_score,
        active_note_names,
        pitch_classes,
        best_root,
        bass,
        candidates,
        candidate_notes,
        candidate_aliases,
        candidate_explanations,
        note_weights,
    )


def identify_chord(pitches: list[int]) -> tuple[str | None, float]:
    analysis = analyze_chord(pitches)
    return analysis.label, analysis.confidence


def midi_note_name(pitch: int, spelling_preference: str | None = "auto") -> str:
    return spell_midi_note_name(pitch, spelling_preference)
