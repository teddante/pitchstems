from __future__ import annotations

from dataclasses import dataclass, field

from pitchstems.editor_project import (
    ChordRegion,
    NoteEvent,
    PITCH_NAMES,
    chord_pitch_classes_for_label,
    midi_velocity_energy,
)


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


SCALE_REGISTRY: tuple[ScaleDefinition, ...] = (
    ScaleDefinition("Ionian", (0, 2, 4, 5, 7, 9, 11), "diatonic", ("major",)),
    ScaleDefinition("Dorian", (0, 2, 3, 5, 7, 9, 10), "diatonic"),
    ScaleDefinition("Phrygian", (0, 1, 3, 5, 7, 8, 10), "diatonic"),
    ScaleDefinition("Lydian", (0, 2, 4, 6, 7, 9, 11), "diatonic"),
    ScaleDefinition("Mixolydian", (0, 2, 4, 5, 7, 9, 10), "diatonic"),
    ScaleDefinition("Aeolian", (0, 2, 3, 5, 7, 8, 10), "diatonic", ("natural minor",)),
    ScaleDefinition("Locrian", (0, 1, 3, 5, 6, 8, 10), "diatonic"),
    ScaleDefinition("Harmonic minor", (0, 2, 3, 5, 7, 8, 11), "minor"),
    ScaleDefinition("Melodic minor", (0, 2, 3, 5, 7, 9, 11), "minor"),
    ScaleDefinition("Dorian b2", (0, 1, 3, 5, 7, 9, 10), "melodic minor mode"),
    ScaleDefinition("Lydian augmented", (0, 2, 4, 6, 8, 9, 11), "melodic minor mode"),
    ScaleDefinition("Lydian dominant", (0, 2, 4, 6, 7, 9, 10), "melodic minor mode"),
    ScaleDefinition("Mixolydian b6", (0, 2, 4, 5, 7, 8, 10), "melodic minor mode"),
    ScaleDefinition("Locrian natural 2", (0, 2, 3, 5, 6, 8, 10), "melodic minor mode"),
    ScaleDefinition("Altered", (0, 1, 3, 4, 6, 8, 10), "melodic minor mode"),
    ScaleDefinition("Major pentatonic", (0, 2, 4, 7, 9), "pentatonic"),
    ScaleDefinition("Minor pentatonic", (0, 3, 5, 7, 10), "pentatonic"),
    ScaleDefinition("Suspended pentatonic", (0, 2, 5, 7, 10), "pentatonic"),
    ScaleDefinition("Major blues", (0, 2, 3, 4, 7, 9), "blues"),
    ScaleDefinition("Minor blues", (0, 3, 5, 6, 7, 10), "blues"),
    ScaleDefinition("Whole tone", (0, 2, 4, 6, 8, 10), "symmetrical"),
    ScaleDefinition("Diminished half-whole", (0, 1, 3, 4, 6, 7, 9, 10), "symmetrical"),
    ScaleDefinition("Diminished whole-half", (0, 2, 3, 5, 6, 8, 9, 11), "symmetrical"),
    ScaleDefinition("Augmented", (0, 3, 4, 7, 8, 11), "symmetrical"),
    ScaleDefinition("Phrygian dominant", (0, 1, 4, 5, 7, 8, 10), "harmonic minor mode"),
    ScaleDefinition("Double harmonic major", (0, 1, 4, 5, 7, 8, 11), "world/common"),
    ScaleDefinition("Hungarian minor", (0, 2, 3, 6, 7, 8, 11), "world/common"),
    ScaleDefinition("Neapolitan minor", (0, 1, 3, 5, 7, 8, 11), "world/common"),
    ScaleDefinition("Persian", (0, 1, 4, 5, 6, 8, 11), "world/common"),
)

ROMAN_NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")


def analyze_theory_at(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    seconds: float,
) -> TheoryAnalysis:
    active_notes = [note for note in notes if note.start <= seconds < note.end]
    active_chords = [chord for chord in chords if chord.start <= seconds < chord.end]
    totals = {}
    bass_totals = {}
    for note in active_notes:
        weight = midi_velocity_energy(note.velocity)
        _add_pitch_weight(totals, note.pitch % 12, weight)
        if note.pitch < 60:
            _add_pitch_weight(bass_totals, note.pitch % 12, weight)
    return _analyze_evidence(totals, bass_totals, active_chords)


def analyze_theory_region(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    start: float,
    end: float,
) -> TheoryAnalysis:
    if end <= start:
        return _analyze_evidence({}, {}, [])
    totals = {}
    bass_totals = {}
    for note in notes:
        overlap = max(0.0, min(note.end, end) - max(note.start, start))
        if overlap <= 0:
            continue
        weight = overlap * midi_velocity_energy(note.velocity)
        _add_pitch_weight(totals, note.pitch % 12, weight)
        if note.pitch < 60:
            _add_pitch_weight(bass_totals, note.pitch % 12, weight)
    active_chords = [
        chord
        for chord in chords
        if max(0.0, min(chord.end, end) - max(chord.start, start)) > 0
    ]
    return _analyze_evidence(totals, bass_totals, active_chords)


def theory_analysis_report(analysis: TheoryAnalysis) -> str:
    lines = [
        "Theory Inspector Calculation",
        "============================",
        f"Detected interpretation: {analysis.label or 'No clear key/mode'} ({analysis.confidence:.0%})",
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
) -> TheoryAnalysis:
    total_energy = sum(totals.values())
    if total_energy <= 0:
        return TheoryAnalysis(None, 0.0, [], [])
    note_weights = _normalized_note_weights(totals)
    chord_root_totals = _chord_root_totals(chords)
    candidates = _scale_candidates(totals, bass_totals, chord_root_totals, chords)
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
) -> list[ScaleCandidate]:
    total_energy = sum(totals.values())
    candidates: list[ScaleCandidate] = []
    for root in range(12):
        for scale in SCALE_REGISTRY:
            pitch_classes = {(root + interval) % 12 for interval in scale.intervals}
            in_energy = sum(weight for pitch_class, weight in totals.items() if pitch_class in pitch_classes)
            pitch_fit = in_energy / total_energy if total_energy else 0.0
            outside_energy = 1.0 - pitch_fit
            center_strength = _center_strength(root, totals, bass_totals, chord_root_totals)
            chord_support = _chord_support(pitch_classes, chords)
            score = pitch_fit * (0.5 + 0.5 * center_strength) * (0.75 + 0.25 * chord_support)
            if pitch_fit < 0.72 and scale.name != "Chromatic":
                continue
            notes = [PITCH_NAMES[(root + interval) % 12] for interval in scale.intervals]
            label = _scale_label(root, scale)
            candidates.append(
                ScaleCandidate(
                    label=label,
                    root=root,
                    scale=scale,
                    notes=notes,
                    score=score,
                    pitch_fit=fit_clamp(pitch_fit),
                    outside_energy=fit_clamp(outside_energy),
                    center_strength=fit_clamp(center_strength),
                    chord_support=fit_clamp(chord_support),
                    explanation=[
                        f"{label} is scored from formal scale membership plus tonal-centre evidence.",
                        "Score formula: pitch_fit * (0.5 + 0.5 * center_strength) "
                        "* (0.75 + 0.25 * chord_support).",
                    ],
                )
            )
    candidates.sort(
        key=lambda candidate: (
            candidate.score,
            candidate.pitch_fit,
            candidate.center_strength,
            -len(candidate.scale.intervals),
        ),
        reverse=True,
    )
    return candidates[:48]


def _scale_label(root: int, scale: ScaleDefinition) -> str:
    root_name = PITCH_NAMES[root]
    if scale.name == "Ionian":
        return f"{root_name} major"
    if scale.name == "Aeolian":
        return f"{root_name} natural minor"
    return f"{root_name} {scale.name}"


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
        return f"{PITCH_NAMES[root]}"
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
    core_notes = [PITCH_NAMES[pitch_class] for pitch_class in core_pitch_classes]
    scale_notes = [
        PITCH_NAMES[pitch_class]
        for pitch_class in scale_pitch_classes
        if pitch_class not in set(core_pitch_classes)
    ]
    outside_notes = [
        PITCH_NAMES[pitch_class]
        for pitch_class in range(12)
        if pitch_class not in set(scale_pitch_classes)
    ]
    return core_notes, scale_notes, outside_notes


def _normalized_note_weights(totals: dict[int, float]) -> list[tuple[str, float]]:
    max_total = max(totals.values(), default=0.0)
    if max_total <= 0:
        return []
    return [
        (PITCH_NAMES[pitch_class], totals[pitch_class] / max_total)
        for pitch_class in sorted(totals, key=lambda item: totals[item], reverse=True)
    ]


def _chord_root_totals(chords: list[ChordRegion]) -> dict[int, float]:
    totals: dict[int, float] = {}
    for chord in chords:
        root = _chord_root(chord.label)
        if root is not None:
            _add_pitch_weight(totals, root, chord.duration)
    return totals


def _chord_root(label: str) -> int | None:
    base_label = label.split("/", 1)[0]
    root_name = next(
        (
            name
            for name in sorted(PITCH_NAMES, key=len, reverse=True)
            if base_label.startswith(name)
        ),
        None,
    )
    if root_name is None:
        return None
    return PITCH_NAMES.index(root_name)


def _chord_suffix(label: str) -> str:
    base_label = label.split("/", 1)[0]
    root_name = next(
        (
            name
            for name in sorted(PITCH_NAMES, key=len, reverse=True)
            if base_label.startswith(name)
        ),
        "",
    )
    return base_label[len(root_name):]


def _minor_or_diminished_suffix(suffix: str) -> bool:
    return suffix.startswith("m") and not suffix.startswith("maj") or "dim" in suffix


def _add_pitch_weight(totals: dict[int, float], pitch_class: int, weight: float) -> None:
    totals[pitch_class] = totals.get(pitch_class, 0.0) + weight


def fit_clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
