from __future__ import annotations

from dataclasses import dataclass

from pitchstems.chord_naming import PITCH_NAMES, _chord_qualities, chord_pitch_classes_for_label
from pitchstems.notation import normalized_pitch_class_weights, split_chord_label

MIN_WEIGHTED_TONE_SUPPORT = 0.005
PARTIAL_HINT_LIMIT = 6


@dataclass(frozen=True)
class ChordScoringOptions:
    weak_note_floor: float = 0.0


@dataclass(frozen=True)
class PartialChordCandidate:
    label: str
    score: float
    observed_tones: list[int]
    omitted_tone: int
    full_tones: list[int]
    explanation: list[str]


def _ordered_pitch_classes(pitch_classes: set[int], root: int | None = None) -> list[int]:
    if root is None or root not in pitch_classes:
        return sorted(pitch_classes)
    return sorted(pitch_classes, key=lambda pitch_class: (pitch_class - root) % 12)


def _interval_quality_name(interval: int) -> str:
    return {
        0: "unison",
        1: "minor second",
        2: "major second",
        3: "minor third",
        4: "major third",
        5: "perfect fourth",
        6: "tritone",
        7: "perfect fifth",
        8: "minor sixth",
        9: "major sixth",
        10: "minor seventh",
        11: "major seventh",
    }[interval % 12]


def _interval_names(root: int, intervals) -> list[str]:
    return [PITCH_NAMES[(root + interval) % 12] for interval in intervals]


def _score_root(
    root: int,
    pitch_classes: set[int],
    bass: int,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> tuple[str, float, list[str], tuple[float, ...]] | None:
    intervals = {(pitch - root) % 12 for pitch in pitch_classes}
    best_quality = ""
    best_score = 0.0
    best_explanation: list[str] = []
    best_rank_key: tuple[float, ...] = ()
    for suffix, required in _chord_qualities():
        label = f"{PITCH_NAMES[root]}{suffix}"
        if bass != root:
            label = f"{label}/{PITCH_NAMES[bass]}"
        if not _label_matches_constraints(label, required_pitch_classes, excluded_pitch_classes):
            continue
        required_set = set(required)
        matched = len(intervals & required_set)
        extras = len(intervals - required_set)
        missing = len(required_set - intervals)
        coverage = matched / len(required_set)
        purity = matched / max(1, len(intervals))
        score = coverage * purity
        rank_key = _plain_chord_rank_key(
            score,
            missing,
            extras,
            intervals == required_set,
            root == bass,
            root in pitch_classes,
            len(required_set),
        )
        if rank_key > best_rank_key:
            best_quality = suffix
            best_score = score
            best_rank_key = rank_key
            best_explanation = _plain_score_explanation(
                label=label,
                root=root,
                required=required,
                intervals=intervals,
                matched=matched,
                coverage=coverage,
                purity=purity,
                score=score,
            )
    label = f"{PITCH_NAMES[root]}{best_quality}"
    if bass != root:
        label = f"{label}/{PITCH_NAMES[bass]}"
    if not best_explanation:
        return None
    return label, max(0.0, min(1.0, best_score)), best_explanation, best_rank_key


def _normalized_note_weights(pitch_weights: dict[int, float]) -> list[tuple[str, float]]:
    return normalized_pitch_class_weights(pitch_weights)


def _score_weighted_root_candidates(
    root: int,
    pitch_weights: dict[int, float],
    bass: int,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> list[tuple[str, float, list[str], tuple[float, ...]]]:
    interval_weights = {
        (pitch - root) % 12: weight
        for pitch, weight in pitch_weights.items()
    }
    total_weight = max(0.0001, sum(interval_weights.values()))
    max_weight = max(interval_weights.values())
    candidates: list[tuple[str, float, list[str], tuple[float, ...]]] = []
    for suffix, required in _chord_qualities():
        label = f"{PITCH_NAMES[root]}{suffix}"
        if bass != root:
            label = f"{label}/{PITCH_NAMES[bass]}"
        if not _label_matches_constraints(label, required_pitch_classes, excluded_pitch_classes):
            continue
        required_set = set(required)
        normalized_support = {
            interval: interval_weights.get(interval, 0.0) / max_weight
            for interval in required_set
        }
        unsupported = {
            interval
            for interval, support in normalized_support.items()
            if support < MIN_WEIGHTED_TONE_SUPPORT
            and (
                not required_pitch_classes
                or (root + interval) % 12 not in required_pitch_classes
            )
        }
        if unsupported:
            continue
        template_weight = sum(interval_weights.get(interval, 0.0) for interval in required)
        required_weight = template_weight / total_weight
        extra_weight = 1.0 - required_weight
        missing = sum(1 for interval in required_set if interval not in interval_weights)
        coverage = sum(
            min(1.0, interval_weights.get(interval, 0.0) / max_weight)
            for interval in required
        ) / len(required)
        score = coverage * required_weight
        rank_key = _weighted_chord_rank_key(
            score,
            missing,
            extra_weight,
            root == bass,
            root in pitch_weights,
            len(required_set),
        )
        explanation = _weighted_score_explanation(
            label=label,
            root=root,
            required=required,
            interval_weights=interval_weights,
            required_weight=required_weight,
            extra_weight=extra_weight,
            coverage=coverage,
            score=score,
        )
        candidates.append((label, max(0.0, min(1.0, score)), explanation, rank_key))
    return candidates


def _plain_chord_rank_key(
    score: float,
    missing: int,
    extras: int,
    exact_match: bool,
    bass_is_root: bool,
    root_is_present: bool,
    required_count: int,
) -> tuple[float, ...]:
    return (
        score,
        -float(missing),
        -float(extras),
        1.0 if exact_match else 0.0,
        1.0 if bass_is_root else 0.0,
        1.0 if root_is_present else 0.0,
        -float(required_count),
    )


def _weighted_chord_rank_key(
    score: float,
    missing: int,
    extra_weight: float,
    bass_is_root: bool,
    root_is_present: bool,
    required_count: int,
) -> tuple[float, ...]:
    return (
        score,
        -float(missing),
        -extra_weight,
        1.0 if bass_is_root else 0.0,
        1.0 if root_is_present else 0.0,
        -float(required_count),
    )


def _candidate_labels(
    scored_roots,
    threshold: float,
    margin: float,
    best_score: float,
    pitch_classes: set[int],
) -> list[tuple[str, float]]:
    candidates: list[tuple[str, float]] = []
    seen_note_sets: set[frozenset[int]] = set()
    for item in scored_roots:
        label, score = item[0], item[1]
        notes = set(chord_pitch_classes_for_label(label))
        is_close = score >= threshold and score >= best_score - margin
        is_exact_alias = notes == pitch_classes
        note_key = frozenset(notes)
        if note_key in seen_note_sets:
            continue
        if is_close or is_exact_alias:
            candidates.append((label, score))
            seen_note_sets.add(note_key)
    return candidates[:8]


def _partial_shell_candidates_from_weights(
    pitch_weights: dict[int, float],
    bass: int | None = None,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> list[PartialChordCandidate]:
    if len(pitch_weights) < 3:
        return []
    required_pitch_classes = required_pitch_classes or set()
    excluded_pitch_classes = excluded_pitch_classes or set()
    sorted_weights = sorted(pitch_weights.items(), key=lambda item: (-item[1], item[0]))
    primary = dict(sorted_weights[:3])
    observed = set(primary)
    if required_pitch_classes and not required_pitch_classes <= observed:
        observed |= required_pitch_classes
    if excluded_pitch_classes and observed & excluded_pitch_classes:
        return []
    total_weight = max(sum(pitch_weights.values()), 0.0001)
    observed_weight = sum(pitch_weights.get(pitch_class, 0.0) for pitch_class in observed)
    suggestions: list[tuple[int, int, int, int, tuple[int, ...], PartialChordCandidate]] = []
    seen_labels: set[str] = set()
    for root in range(12):
        for quality_index, (suffix, intervals) in enumerate(_chord_qualities()):
            if "(no" in suffix or len(intervals) < 4:
                continue
            full_tones = [(root + interval) % 12 for interval in intervals]
            full_set = set(full_tones)
            if not observed <= full_set:
                continue
            missing = full_set - observed
            if len(missing) != 1:
                continue
            omitted_tone = next(iter(missing))
            omitted_interval = (omitted_tone - root) % 12
            omitted = _omitted_tone_suffix(omitted_interval)
            if omitted is None:
                continue
            candidate_tones = [pitch_class for pitch_class in full_tones if pitch_class != omitted_tone]
            label = f"{PITCH_NAMES[root]}{suffix}{omitted}"
            if bass is not None and bass in observed and bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            if label in seen_labels:
                continue
            if not _label_matches_constraints(label, required_pitch_classes, excluded_pitch_classes):
                continue
            score = (observed_weight / total_weight) * (len(observed) / len(full_set))
            explanation = [
                f"{label}: partial shell from the strongest detected notes.",
                f"Observed shell tones: {' - '.join(PITCH_NAMES[pitch_class] for pitch_class in candidate_tones)}.",
                f"Full chord shape would be: {' - '.join(PITCH_NAMES[pitch_class] for pitch_class in full_tones)}.",
                f"Omitted tone: {PITCH_NAMES[omitted_tone]} ({omitted[1:-1]}).",
                "This is a partial/shell candidate, not a full chord detection.",
            ]
            seen_labels.add(label)
            root_priority = 0 if bass is not None and root == bass else 1
            observed_root_priority = 0 if root in observed else 1
            omitted_priority = 0 if omitted == "(no5)" else 1
            suggestions.append(
                (
                    root_priority,
                    omitted_priority,
                    observed_root_priority,
                    _partial_quality_priority(suffix, quality_index),
                    tuple(candidate_tones),
                    PartialChordCandidate(
                        label=label,
                        score=max(0.0, min(1.0, score)),
                        observed_tones=candidate_tones,
                        omitted_tone=omitted_tone,
                        full_tones=full_tones,
                        explanation=explanation,
                    ),
                )
            )
    suggestions.sort(key=lambda item: (item[1], item[0], item[2], item[3], item[4]))
    candidates: list[PartialChordCandidate] = []
    seen_root_tone_sets: set[tuple[int, frozenset[int]]] = set()
    for *_sort, candidate in suggestions:
        parts = split_chord_label(candidate.label)
        if parts is None:
            continue
        root_tone_key = (parts.root_pitch_class, frozenset(candidate.observed_tones))
        if root_tone_key in seen_root_tone_sets:
            continue
        candidates.append(candidate)
        seen_root_tone_sets.add(root_tone_key)
        if len(candidates) >= PARTIAL_HINT_LIMIT:
            break
    return candidates


def _omitted_tone_suffix(omitted_interval: int) -> str | None:
    if omitted_interval == 7:
        return "(no5)"
    if omitted_interval in {3, 4}:
        return "(no3)"
    return None


def _partial_chord_completions(
    observed: set[int],
    bass: int | None = None,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> list[str]:
    required_pitch_classes = required_pitch_classes or set()
    excluded_pitch_classes = excluded_pitch_classes or set()
    suggestions: list[tuple[int, int, int, int, int, tuple[int, ...], frozenset[int], str]] = []
    for root in range(12):
        for quality_index, (suffix, intervals) in enumerate(_chord_qualities()):
            tones = {(root + interval) % 12 for interval in intervals}
            if not observed <= tones:
                continue
            if required_pitch_classes and not required_pitch_classes <= tones:
                continue
            if excluded_pitch_classes and tones & excluded_pitch_classes:
                continue
            missing = tones - observed
            if not missing or len(missing) > 2:
                continue
            note_key = frozenset(tones)
            label = f"{PITCH_NAMES[root]}{suffix}"
            if bass is not None and bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            missing_text = "add " + "-".join(
                PITCH_NAMES[pitch_class]
                for pitch_class in _ordered_pitch_classes(missing, root)
            )
            root_priority = 0 if bass is not None and root == bass else 1
            observed_root_priority = 0 if root in observed else 1
            suggestions.append(
                (
                    len(missing),
                    root_priority,
                    observed_root_priority,
                    len(tones),
                    _partial_quality_priority(suffix, quality_index),
                    tuple(sorted(note_key)),
                    note_key,
                    f"{label} ({missing_text})",
                )
            )
    suggestions.sort()
    completions: list[str] = []
    seen_note_sets: set[frozenset[int]] = set()
    for *_sort, note_key, label in suggestions:
        if note_key in seen_note_sets:
            continue
        completions.append(label)
        seen_note_sets.add(note_key)
        if len(completions) >= PARTIAL_HINT_LIMIT:
            break
    return completions


def _partial_quality_priority(suffix: str, fallback: int) -> int:
    priorities = {
        "": 0,
        "m": 1,
        "sus2": 2,
        "sus4": 3,
        "dim": 4,
        "aug": 5,
        "6": 6,
        "m6": 7,
        "7": 8,
        "maj7": 9,
        "m7": 10,
        "add9": 11,
        "madd9": 12,
        "add4": 13,
        "add11": 14,
    }
    return priorities.get(suffix, 100 + fallback)


def _perfect_fifth_root(pitch_classes: set[int], preferred_root: int) -> int | None:
    if len(pitch_classes) != 2:
        return None
    if (preferred_root + 7) % 12 in pitch_classes:
        return preferred_root
    for pitch_class in pitch_classes:
        if (pitch_class + 7) % 12 in pitch_classes:
            return pitch_class
    return None


def _label_matches_constraints(
    label: str,
    required_pitch_classes: set[int] | None,
    excluded_pitch_classes: set[int] | None,
) -> bool:
    notes = set(chord_pitch_classes_for_label(label))
    if required_pitch_classes and not required_pitch_classes <= notes:
        return False
    return not (excluded_pitch_classes and notes & excluded_pitch_classes)


def _plain_score_explanation(
    label: str,
    root: int,
    required: tuple[int, ...],
    intervals: set[int],
    matched: int,
    coverage: float,
    purity: float,
    score: float,
) -> list[str]:
    required_set = set(required)
    matched_notes = _interval_names(root, sorted(intervals & required_set))
    missing_notes = _interval_names(root, sorted(required_set - intervals))
    extra_notes = _interval_names(root, sorted(intervals - required_set))
    return [
        f"{label}: scored from the notes active at the playhead.",
        f"Chord tones expected: {' - '.join(_interval_names(root, required))}.",
        f"Matched tones: {', '.join(matched_notes) or 'none'} ({matched}/{len(required_set)}).",
        f"Missing tones: {', '.join(missing_notes) or 'none'}. Extra active tones: {', '.join(extra_notes) or 'none'}.",
        f"Evidence terms: coverage {coverage:.0%}, purity {purity:.0%}.",
        "Ranking rule: prefer higher unweighted evidence, then fewer missing tones, fewer extra tones, exact note-set matches, and bass/root agreement.",
        "Display score: coverage * purity. No naming bonuses, penalties, or user-tuned weights are applied.",
        f"Raw score {score:.2f}; displayed percentage is a ranking score, not a statistical probability.",
    ]


def _weighted_score_explanation(
    label: str,
    root: int,
    required: tuple[int, ...],
    interval_weights: dict[int, float],
    required_weight: float,
    extra_weight: float,
    coverage: float,
    score: float,
) -> list[str]:
    required_set = set(required)
    total_weight = sum(interval_weights.values())
    matched_notes = [
        f"{PITCH_NAMES[(root + interval) % 12]} {interval_weights[interval] / total_weight:.0%}"
        for interval in required
        if interval in interval_weights
    ]
    missing_notes = _interval_names(root, sorted(required_set - set(interval_weights)))
    extra_notes = [
        f"{PITCH_NAMES[(root + interval) % 12]} {weight / total_weight:.0%}"
        for interval, weight in sorted(interval_weights.items())
        if interval not in required_set
    ]
    return [
        f"{label}: scored from weighted notes across the selected time range.",
        f"Chord tones expected: {' - '.join(_interval_names(root, required))}.",
        f"Matched weighted tones: {', '.join(matched_notes) or 'none'}; candidate-tone energy {required_weight:.0%}.",
        f"Missing tones: {', '.join(missing_notes) or 'none'}. Extra weighted tones: {', '.join(extra_notes) or 'none'} ({extra_weight:.0%}).",
        f"Evidence terms: coverage {coverage:.0%}, purity {required_weight:.0%}.",
        "Ranking rule: prefer higher unweighted evidence, then fewer missing tones, less extra energy, and bass/root agreement.",
        "Display score: coverage * purity. No naming bonuses, penalties, or user-tuned weights are applied.",
        f"Raw score {score:.2f}; displayed percentage is a ranking score, not a statistical probability.",
    ]
