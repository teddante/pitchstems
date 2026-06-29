from __future__ import annotations

from dataclasses import dataclass, field

from pitchstems.chord_analysis import chord_pitch_classes_for_label
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.midi_energy import (
    active_notes_at,
    midi_velocity_energy,
    note_overlap_seconds,
    point_pitch_energy,
    region_pitch_energy,
)
from pitchstems.notation import (
    normalized_pitch_class_weights,
    pitch_class_name,
    scale_label,
    spell_scale,
    spelling_preference_from_label,
    split_chord_label,
)
from pitchstems.theory_helpers import (
    candidate_common_tones as _candidate_common_tones,
    candidate_pitch_class_movement as _candidate_pitch_class_movement,
    candidate_theory_fit as _candidate_theory_fit,
    diatonic_chord_labels as _diatonic_chord_labels,
    fit_clamp,
    next_chord as _next_chord,
    previous_chord as _previous_chord,
    region_energy as _region_energy,
    report_time as _report_time,
)

__all__ = [
    "ScaleCandidate",
    "ScaleDefinition",
    "TheoryAnalysis",
    "analyze_theory_at",
    "analyze_theory_region",
    "fit_clamp",
    "theory_analysis_report",
    "_candidate_common_tones",
    "_candidate_pitch_class_movement",
    "_candidate_theory_fit",
    "_diatonic_chord_labels",
    "_next_chord",
    "_previous_chord",
    "_region_energy",
    "_report_time",
]


@dataclass(frozen=True)
class ScaleDefinition:
    name: str
    intervals: tuple[int, ...]
    family: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScaleCandidate:
    label: str
    root: int
    scale: ScaleDefinition
    notes: list[str]
    score: float
    pitch_fit: float
    outside_energy: float
    center_strength: float
    chord_support: float
    explanation: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProgressionInterpretation:
    candidate_label: str
    chord_labels: list[str]
    roman_numerals: list[str]


@dataclass(frozen=True)
class TheoryAnalysis:
    label: str | None
    confidence: float
    note_weights: list[tuple[str, float]]
    candidates: list[ScaleCandidate]
    progression: ProgressionInterpretation | None = None
    core_notes: list[str] = field(default_factory=list)
    scale_notes: list[str] = field(default_factory=list)
    outside_notes: list[str] = field(default_factory=list)


def _scale(
    name: str,
    intervals: tuple[int, ...],
    family: str,
    aliases: tuple[str, ...] = (),
) -> ScaleDefinition:
    return ScaleDefinition(name, intervals, family, aliases)


def _modes(
    parent_intervals: tuple[int, ...],
    mode_names: tuple[str, ...],
    family: str,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> list[ScaleDefinition]:
    aliases = aliases or {}
    modes = []
    for index, name in enumerate(mode_names):
        root = parent_intervals[index]
        rotated = parent_intervals[index:] + tuple(interval + 12 for interval in parent_intervals[:index])
        intervals = tuple((interval - root) % 12 for interval in rotated)
        modes.append(_scale(name, intervals, family, aliases.get(name, ())))
    return modes


def _scale_registry() -> tuple[ScaleDefinition, ...]:
    major = (0, 2, 4, 5, 7, 9, 11)
    melodic_minor = (0, 2, 3, 5, 7, 9, 11)
    harmonic_minor = (0, 2, 3, 5, 7, 8, 11)
    harmonic_major = (0, 2, 4, 5, 7, 8, 11)
    double_harmonic = (0, 1, 4, 5, 7, 8, 11)

    scales = [
        *_modes(
            major,
            ("Ionian", "Dorian", "Phrygian", "Lydian", "Mixolydian", "Aeolian", "Locrian"),
            "diatonic",
            aliases={"Ionian": ("major",), "Aeolian": ("natural minor",)},
        ),
        *_modes(
            melodic_minor,
            (
                "Melodic minor",
                "Dorian b2",
                "Lydian augmented",
                "Lydian dominant",
                "Mixolydian b6",
                "Locrian natural 2",
                "Altered",
            ),
            "melodic minor mode",
            aliases={"Lydian dominant": ("Acoustic",), "Altered": ("Super Locrian",)},
        ),
        *_modes(
            harmonic_minor,
            (
                "Harmonic minor",
                "Locrian natural 6",
                "Ionian augmented",
                "Dorian #4",
                "Phrygian dominant",
                "Lydian #2",
                "Altered diminished",
            ),
            "harmonic minor mode",
            aliases={"Dorian #4": ("Ukrainian Dorian",), "Phrygian dominant": ("Spanish gypsy",)},
        ),
        *_modes(
            harmonic_major,
            (
                "Harmonic major",
                "Dorian b5",
                "Phrygian b4",
                "Lydian b3",
                "Mixolydian b2",
                "Lydian augmented #2",
                "Locrian bb7",
            ),
            "harmonic major mode",
        ),
        *_modes(
            double_harmonic,
            (
                "Double harmonic major",
                "Lydian #2 #6",
                "Ultraphrygian",
                "Hungarian minor",
                "Oriental",
                "Ionian augmented #2",
                "Locrian bb3 bb7",
            ),
            "double harmonic mode",
        ),
        _scale("Major pentatonic", (0, 2, 4, 7, 9), "pentatonic"),
        _scale("Minor pentatonic", (0, 3, 5, 7, 10), "pentatonic"),
        _scale("Suspended pentatonic", (0, 2, 5, 7, 10), "pentatonic"),
        _scale("Egyptian pentatonic", (0, 2, 5, 7, 10), "pentatonic"),
        _scale("Hirajoshi", (0, 2, 3, 7, 8), "pentatonic"),
        _scale("In-sen", (0, 1, 5, 7, 10), "pentatonic"),
        _scale("Iwato", (0, 1, 5, 6, 10), "pentatonic"),
        _scale("Kumoi", (0, 2, 3, 7, 9), "pentatonic"),
        _scale("Yo", (0, 2, 5, 7, 9), "pentatonic"),
        _scale("Pelog", (0, 1, 3, 7, 8), "pentatonic"),
        _scale("Major blues", (0, 2, 3, 4, 7, 9), "blues"),
        _scale("Minor blues", (0, 3, 5, 6, 7, 10), "blues"),
        _scale("Bebop major", (0, 2, 4, 5, 7, 8, 9, 11), "bebop"),
        _scale("Bebop dominant", (0, 2, 4, 5, 7, 9, 10, 11), "bebop"),
        _scale("Bebop minor", (0, 2, 3, 5, 7, 8, 9, 10), "bebop"),
        _scale("Bebop Dorian", (0, 2, 3, 4, 5, 7, 9, 10), "bebop"),
        _scale("Whole tone", (0, 2, 4, 6, 8, 10), "symmetrical"),
        _scale("Diminished half-whole", (0, 1, 3, 4, 6, 7, 9, 10), "symmetrical"),
        _scale("Diminished whole-half", (0, 2, 3, 5, 6, 8, 9, 11), "symmetrical"),
        _scale("Augmented", (0, 3, 4, 7, 8, 11), "symmetrical"),
        _scale("Tritone", (0, 1, 4, 6, 7, 10), "symmetrical"),
        _scale("Chromatic", tuple(range(12)), "symmetrical/complete"),
        _scale("Major hexatonic", (0, 2, 4, 5, 7, 9), "hexatonic"),
        _scale("Minor hexatonic", (0, 2, 3, 5, 7, 10), "hexatonic"),
        _scale("Prometheus", (0, 2, 4, 6, 9, 10), "hexatonic"),
        _scale("Blues diminished", (0, 3, 5, 6, 7, 9, 10), "blues"),
        _scale("Neapolitan minor", (0, 1, 3, 5, 7, 8, 11), "world/common"),
        _scale("Neapolitan major", (0, 1, 3, 5, 7, 9, 11), "world/common"),
        _scale("Hungarian major", (0, 3, 4, 6, 7, 9, 10), "world/common"),
        _scale("Romanian minor", (0, 2, 3, 6, 7, 9, 10), "world/common"),
        _scale("Persian", (0, 1, 4, 5, 6, 8, 11), "world/common"),
        _scale("Enigmatic", (0, 1, 4, 6, 8, 10, 11), "world/common"),
        _scale("Leading whole tone", (0, 2, 4, 6, 8, 10, 11), "world/common"),
        _scale("Raga Bhairav", (0, 1, 4, 5, 7, 8, 11), "raga/common"),
        _scale("Raga Todi", (0, 1, 3, 6, 7, 8, 11), "raga/common"),
        _scale("Raga Marwa", (0, 1, 4, 6, 7, 9, 11), "raga/common"),
        _scale("Raga Purvi", (0, 1, 4, 6, 7, 8, 11), "raga/common"),
    ]
    return tuple(scales)


SCALE_REGISTRY: tuple[ScaleDefinition, ...] = _scale_registry()

ROMAN_NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")


def analyze_theory_at(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    seconds: float,
    *,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> TheoryAnalysis:
    active_notes = active_notes_at(notes, seconds)
    active_chords = [chord for chord in chords if chord.start <= seconds < chord.end]
    totals, _exact_pitch_weights = point_pitch_energy(notes, seconds)
    totals = _constrained_totals(totals, required_pitch_classes, excluded_pitch_classes)
    bass_totals = {}
    for note in active_notes:
        weight = midi_velocity_energy(note.velocity)
        if note.pitch < 60:
            _add_pitch_weight(bass_totals, note.pitch % 12, weight)
    bass_totals = _constrained_totals(bass_totals, None, excluded_pitch_classes)
    return _analyze_evidence(totals, bass_totals, active_chords, required_pitch_classes, excluded_pitch_classes)


def analyze_theory_region(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    start: float,
    end: float,
    *,
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> TheoryAnalysis:
    if end <= start:
        return _analyze_evidence({}, {}, [], required_pitch_classes, excluded_pitch_classes)
    totals, _exact_pitch_weights = region_pitch_energy(notes, start, end)
    totals = _constrained_totals(totals, required_pitch_classes, excluded_pitch_classes)
    bass_totals = {}
    for note in notes:
        overlap = note_overlap_seconds(note, start, end)
        if overlap <= 0:
            continue
        weight = overlap * midi_velocity_energy(note.velocity)
        if note.pitch < 60:
            _add_pitch_weight(bass_totals, note.pitch % 12, weight)
    bass_totals = _constrained_totals(bass_totals, None, excluded_pitch_classes)
    active_chords = [
        chord
        for chord in chords
        if max(0.0, min(chord.end, end) - max(chord.start, start)) > 0
    ]
    return _analyze_evidence(totals, bass_totals, active_chords, required_pitch_classes, excluded_pitch_classes)


def theory_analysis_report(analysis: TheoryAnalysis) -> str:
    lines = [
        "Theory Inspector Calculation",
        "============================",
        f"Detected interpretation: {analysis.label or 'No clear key/mode'} (ranking score {analysis.confidence:.0%})",
        "",
        "Pitch Evidence",
        "--------------",
        "MIDI energy model: note energy = overlap_seconds * (velocity / 127)^2.",
        "Pitch classes are summed across octaves and selected analysis tracks.",
        "",
        "Weighted Pitch Classes",
        "----------------------",
    ]
    if analysis.note_weights:
        lines.extend(f"{name:>2}: {weight:.0%}" for name, weight in analysis.note_weights)
    else:
        lines.append("-")
    lines.extend(["", "Scale / Key / Mode Candidates", "-----------------------------"])
    if not analysis.candidates:
        lines.append("No candidates. There is not enough pitch evidence.")
    for candidate in analysis.candidates:
        lines.extend(
            [
                "",
                f"{candidate.label} ({candidate.score:.0%})",
                f"Scale notes: {' - '.join(candidate.notes)}",
                f"Family: {candidate.scale.family}",
                f"Aliases: {', '.join(candidate.scale.aliases) or '-'}",
                f"Pitch fit: {candidate.pitch_fit:.0%}",
                f"Outside energy: {candidate.outside_energy:.0%}",
                f"Tonal-centre strength: {candidate.center_strength:.0%}",
                f"Chord support: {candidate.chord_support:.0%}",
                *candidate.explanation,
            ]
        )
    if analysis.progression:
        lines.extend(
            [
                "",
                "Progression",
                "-----------",
                f"Chords: {' - '.join(analysis.progression.chord_labels) or '-'}",
                f"In {analysis.progression.candidate_label}: "
                f"{' - '.join(analysis.progression.roman_numerals) or '-'}",
            ]
        )
    lines.extend(
        [
            "",
            "Suggested Note Groups",
            "---------------------",
            f"Core chord tones: {' - '.join(analysis.core_notes) or '-'}",
            f"In-scale notes: {' - '.join(analysis.scale_notes) or '-'}",
            f"Outside notes: {' - '.join(analysis.outside_notes) or '-'}",
        ]
    )
    return "\n".join(lines)


def _analyze_evidence(
    totals: dict[int, float],
    bass_totals: dict[int, float],
    chords: list[ChordRegion],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> TheoryAnalysis:
    total_energy = sum(totals.values())
    if total_energy <= 0:
        return TheoryAnalysis(None, 0.0, [], [])
    note_weights = _normalized_note_weights(totals)
    chord_root_totals = _chord_root_totals(chords)
    candidates = _scale_candidates(
        totals,
        bass_totals,
        chord_root_totals,
        chords,
        required_pitch_classes,
        excluded_pitch_classes,
    )
    best = candidates[0] if candidates else None
    progression = _progression_for_candidate(best, chords) if best else None
    core_notes, scale_notes, outside_notes = _suggested_note_groups(best, chords)
    return TheoryAnalysis(
        label=best.label if best else None,
        confidence=best.score if best else 0.0,
        note_weights=note_weights,
        candidates=candidates,
        progression=progression,
        core_notes=core_notes,
        scale_notes=scale_notes,
        outside_notes=outside_notes,
    )


def _scale_candidates(
    totals: dict[int, float],
    bass_totals: dict[int, float],
    chord_root_totals: dict[int, float],
    chords: list[ChordRegion],
    required_pitch_classes: set[int] | None = None,
    excluded_pitch_classes: set[int] | None = None,
) -> list[ScaleCandidate]:
    total_energy = sum(totals.values())
    observed_pitch_classes = set(totals)
    candidates: list[ScaleCandidate] = []
    for root in range(12):
        for scale in SCALE_REGISTRY:
            pitch_classes = {(root + interval) % 12 for interval in scale.intervals}
            if required_pitch_classes and not required_pitch_classes <= pitch_classes:
                continue
            if excluded_pitch_classes and pitch_classes & excluded_pitch_classes:
                continue
            in_energy = sum(weight for pitch_class, weight in totals.items() if pitch_class in pitch_classes)
            pitch_fit = in_energy / total_energy if total_energy else 0.0
            outside_energy = 1.0 - pitch_fit
            center_strength = _center_strength(root, totals, bass_totals, chord_root_totals)
            chord_support = _chord_support(pitch_classes, chords)
            if pitch_fit < 0.72 and scale.name != "Chromatic":
                continue
            notes = spell_scale(root, scale.intervals)
            label = _scale_label(root, scale)
            candidates.append(
                ScaleCandidate(
                    label=label,
                    root=root,
                    scale=scale,
                    notes=notes,
                    score=fit_clamp(pitch_fit),
                    pitch_fit=fit_clamp(pitch_fit),
                    outside_energy=fit_clamp(outside_energy),
                    center_strength=fit_clamp(center_strength),
                    chord_support=fit_clamp(chord_support),
                    explanation=[
                        f"{label} is ranked as a formal explanation of the observed pitch evidence.",
                        "Ranking rule: reject strong contradictions, then prefer higher explained "
                        "energy, fewer unobserved scale tones, stronger tonal-centre evidence, "
                        "and stronger chord-track support.",
                    ],
                )
            )
    candidates.sort(
        key=lambda candidate: _scale_candidate_sort_key(
            candidate,
            observed_pitch_classes,
        ),
        reverse=True,
    )
    return candidates[:96]


def _constrained_totals(
    totals: dict[int, float],
    required_pitch_classes: set[int] | None,
    excluded_pitch_classes: set[int] | None,
) -> dict[int, float]:
    constrained = {
        pitch_class: weight
        for pitch_class, weight in totals.items()
        if not excluded_pitch_classes or pitch_class not in excluded_pitch_classes
    }
    if required_pitch_classes and constrained:
        floor = max(constrained.values()) * 0.001
        for pitch_class in required_pitch_classes:
            if not excluded_pitch_classes or pitch_class not in excluded_pitch_classes:
                constrained.setdefault(pitch_class, floor)
    return constrained


def _scale_candidate_sort_key(
    candidate: ScaleCandidate,
    observed_pitch_classes: set[int],
) -> tuple[float, ...]:
    scale_tones = {
        (candidate.root + interval) % 12
        for interval in candidate.scale.intervals
    }
    unobserved_scale_tones = len(scale_tones - observed_pitch_classes)
    return (
        -candidate.outside_energy,
        candidate.pitch_fit,
        -float(unobserved_scale_tones),
        candidate.center_strength,
        candidate.chord_support,
        -float(len(scale_tones)),
    )


def _scale_label(root: int, scale: ScaleDefinition) -> str:
    return scale_label(root, scale.intervals, scale.name)


def _center_strength(
    root: int,
    totals: dict[int, float],
    bass_totals: dict[int, float],
    chord_root_totals: dict[int, float],
) -> float:
    terms = []
    max_total = max(totals.values(), default=0.0)
    if max_total:
        terms.append(totals.get(root, 0.0) / max_total)
    max_bass = max(bass_totals.values(), default=0.0)
    if max_bass:
        terms.append(bass_totals.get(root, 0.0) / max_bass)
    max_chord = max(chord_root_totals.values(), default=0.0)
    if max_chord:
        terms.append(chord_root_totals.get(root, 0.0) / max_chord)
    if not terms:
        return 0.0
    return sum(terms) / len(terms)


def _chord_support(pitch_classes: set[int], chords: list[ChordRegion]) -> float:
    weighted_total = 0.0
    supported = 0.0
    for chord in chords:
        duration = chord.duration
        if duration <= 0:
            continue
        tones = set(chord_pitch_classes_for_label(chord.label))
        if not tones:
            continue
        weighted_total += duration
        if tones <= pitch_classes:
            supported += duration
    if weighted_total <= 0:
        return 0.0
    return supported / weighted_total


def _progression_for_candidate(
    candidate: ScaleCandidate,
    chords: list[ChordRegion],
) -> ProgressionInterpretation | None:
    if not chords:
        return None
    chord_labels = []
    roman_numerals = []
    seen = set()
    for chord in sorted(chords, key=lambda item: (item.start, item.end)):
        key = (round(chord.start, 3), round(chord.end, 3), chord.label)
        if key in seen:
            continue
        seen.add(key)
        chord_labels.append(chord.label)
        roman_numerals.append(_roman_for_chord(chord.label, candidate.root, candidate.scale))
    return ProgressionInterpretation(candidate.label, chord_labels, roman_numerals)


def _roman_for_chord(label: str, key_root: int, scale: ScaleDefinition) -> str:
    root = _chord_root(label)
    if root is None:
        return "?"
    relative = (root - key_root) % 12
    try:
        degree_index = scale.intervals.index(relative)
    except ValueError:
        return f"{pitch_class_name(root)}"
    numeral = ROMAN_NUMERALS[degree_index]
    suffix = _chord_suffix(label)
    if _minor_or_diminished_suffix(suffix):
        numeral = numeral.lower()
    if "dim" in suffix:
        numeral += "dim"
    elif "aug" in suffix:
        numeral += "aug"
    elif "maj7" in suffix:
        numeral += "maj7"
    elif "7" in suffix:
        numeral += "7"
    return numeral


def _suggested_note_groups(
    candidate: ScaleCandidate | None,
    chords: list[ChordRegion],
) -> tuple[list[str], list[str], list[str]]:
    if candidate is None:
        return [], [], []
    core_pitch_classes: list[int] = []
    if chords:
        chord = sorted(chords, key=lambda item: item.duration, reverse=True)[0]
        core_pitch_classes = chord_pitch_classes_for_label(chord.label)
    scale_pitch_classes = [(candidate.root + interval) % 12 for interval in candidate.scale.intervals]
    scale_spellings = spell_scale(candidate.root, candidate.scale.intervals)
    core_note_set = set(core_pitch_classes)
    core_notes = [
        pitch_class_name(pitch_class, spelling_preference_from_scale_label(candidate.label))
        for pitch_class in core_pitch_classes
    ]
    scale_notes = [
        note_name
        for pitch_class, note_name in zip(scale_pitch_classes, scale_spellings, strict=True)
        if pitch_class not in core_note_set
    ]
    outside_notes = [
        pitch_class_name(pitch_class, spelling_preference_from_scale_label(candidate.label))
        for pitch_class in range(12)
        if pitch_class not in set(scale_pitch_classes)
    ]
    return core_notes, scale_notes, outside_notes


def _normalized_note_weights(totals: dict[int, float]) -> list[tuple[str, float]]:
    return normalized_pitch_class_weights(totals)


def _chord_root_totals(chords: list[ChordRegion]) -> dict[int, float]:
    totals: dict[int, float] = {}
    for chord in chords:
        root = _chord_root(chord.label)
        if root is not None:
            _add_pitch_weight(totals, root, chord.duration)
    return totals


def _chord_root(label: str) -> int | None:
    parts = split_chord_label(label)
    return parts.root_pitch_class if parts is not None else None


def _chord_suffix(label: str) -> str:
    parts = split_chord_label(label)
    return parts.suffix if parts is not None else ""


def _minor_or_diminished_suffix(suffix: str) -> bool:
    return suffix.startswith("m") and not suffix.startswith("maj") or "dim" in suffix


def spelling_preference_from_scale_label(label: str) -> str:
    return spelling_preference_from_label(label)


def _add_pitch_weight(totals: dict[int, float], pitch_class: int, weight: float) -> None:
    totals[pitch_class] = totals.get(pitch_class, 0.0) + weight
