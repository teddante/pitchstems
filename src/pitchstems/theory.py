from __future__ import annotations

from dataclasses import dataclass, field

from pitchstems.editor_project import (
    ChordAnalysis,
    ChordRegion,
    ChordScoringOptions,
    NoteEvent,
    PITCH_NAMES,
    analyze_chord_region,
    chord_pitch_classes_for_label,
    exact_chord_names_for_pitch_classes,
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


@dataclass(frozen=True)
class ChordGapSuggestion:
    label: str
    score: float
    action: str
    start: float
    end: float
    local_evidence: float
    theory_fit: float
    voice_leading: float
    common_tone_support: float
    explanation: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChordGapAnalysis:
    start: float
    end: float
    previous_chord: ChordRegion | None
    next_chord: ChordRegion | None
    suggestions: list[ChordGapSuggestion]
    local_chord_analysis: ChordAnalysis | None = None
    theory_analysis: TheoryAnalysis | None = None


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


def analyze_chord_gap(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    start: float,
    end: float,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordGapAnalysis:
    start, end = sorted((start, end))
    previous_chord = _previous_chord(chords, start)
    next_chord = _next_chord(chords, end)
    if end <= start:
        return ChordGapAnalysis(start, end, previous_chord, next_chord, [])

    local_chord_analysis = analyze_chord_region(
        notes,
        start,
        end,
        scoring_options=scoring_options,
    )
    context_start = previous_chord.start if previous_chord else start
    context_end = next_chord.end if next_chord else end
    theory_analysis = analyze_theory_region(notes, chords, context_start, context_end)
    suggestions = _gap_suggestions(
        notes,
        start,
        end,
        previous_chord,
        next_chord,
        local_chord_analysis,
        theory_analysis,
    )
    return ChordGapAnalysis(
        start=start,
        end=end,
        previous_chord=previous_chord,
        next_chord=next_chord,
        suggestions=suggestions,
        local_chord_analysis=local_chord_analysis,
        theory_analysis=theory_analysis,
    )


def chord_gap_report(analysis: ChordGapAnalysis) -> str:
    lines = [
        "Chord Gap Suggestions",
        "=====================",
        f"Gap: {_report_time(analysis.start)} - {_report_time(analysis.end)}",
        f"Previous chord: {analysis.previous_chord.label if analysis.previous_chord else '-'}",
        f"Next chord: {analysis.next_chord.label if analysis.next_chord else '-'}",
        "",
        "Evidence Model",
        "--------------",
        "Local MIDI evidence uses the same overlap_seconds * (velocity / 127)^2 energy model.",
        "Theory fit checks formal chord tones against the current scale/key/mode candidate.",
        "Voice-leading uses minimum pitch-class movement on the 12-tone circle.",
        "Common-tone support counts shared pitch classes with neighbouring chord regions.",
        "",
        "Suggestions",
        "-----------",
    ]
    if not analysis.suggestions:
        lines.append("No suggestions. There is not enough gap or context evidence.")
    for suggestion in analysis.suggestions:
        lines.extend(
            [
                "",
                f"{suggestion.label} ({suggestion.score:.0%})",
                f"Action: {suggestion.action}",
                f"Local MIDI evidence: {suggestion.local_evidence:.0%}",
                f"Theory fit: {suggestion.theory_fit:.0%}",
                f"Voice-leading: {suggestion.voice_leading:.0%}",
                f"Common-tone support: {suggestion.common_tone_support:.0%}",
                *suggestion.explanation,
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


def _gap_suggestions(
    notes: list[NoteEvent],
    start: float,
    end: float,
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
    local_chord_analysis: ChordAnalysis,
    theory_analysis: TheoryAnalysis,
) -> list[ChordGapSuggestion]:
    candidates: dict[str, tuple[str, float]] = {}
    if previous_chord is not None:
        candidates[previous_chord.label] = ("extend_previous", 0.0)
    if next_chord is not None:
        candidates.setdefault(next_chord.label, ("start_next", 0.0))
    for label, confidence in local_chord_analysis.candidates[:8]:
        candidates.setdefault(label, ("insert", confidence))
    for label in _diatonic_chord_labels(theory_analysis):
        candidates.setdefault(label, ("insert", 0.0))

    suggestions = []
    gap_note_energy = _region_energy(notes, start, end)
    no_local_evidence = 1.0 if gap_note_energy <= 0 else 0.0
    local_scores = dict(local_chord_analysis.candidates)
    for label, (action, generated_local_score) in candidates.items():
        tones = set(chord_pitch_classes_for_label(label))
        if not tones:
            continue
        local_evidence = max(generated_local_score, local_scores.get(label, 0.0))
        if action in {"extend_previous", "start_next"}:
            local_evidence = max(local_evidence, no_local_evidence)
        theory_fit = _candidate_theory_fit(tones, theory_analysis)
        voice_leading = _candidate_voice_leading(tones, previous_chord, next_chord)
        common_tone_support = _candidate_common_tones(tones, previous_chord, next_chord)
        score = (
            0.40 * local_evidence
            + 0.25 * theory_fit
            + 0.20 * voice_leading
            + 0.15 * common_tone_support
        )
        suggestions.append(
            ChordGapSuggestion(
                label=label,
                score=fit_clamp(score),
                action=action,
                start=start,
                end=end,
                local_evidence=fit_clamp(local_evidence),
                theory_fit=fit_clamp(theory_fit),
                voice_leading=fit_clamp(voice_leading),
                common_tone_support=fit_clamp(common_tone_support),
                explanation=[
                    f"{label} is ranked from local MIDI evidence, formal scale/key fit, "
                    "pitch-class voice-leading, and common tones with neighbour chords.",
                    "Score formula: 0.40*local_evidence + 0.25*theory_fit "
                    "+ 0.20*voice_leading + 0.15*common_tone_support.",
                ],
            )
        )
    suggestions.sort(key=lambda suggestion: suggestion.score, reverse=True)
    return suggestions[:10]


def _diatonic_chord_labels(analysis: TheoryAnalysis) -> list[str]:
    if not analysis.candidates:
        return []
    candidate = analysis.candidates[0]
    intervals = candidate.scale.intervals
    if len(intervals) < 7:
        return []
    labels = []
    for degree_index, interval in enumerate(intervals[:7]):
        root = (candidate.root + interval) % 12
        triad = {
            root,
            (candidate.root + intervals[(degree_index + 2) % 7]) % 12,
            (candidate.root + intervals[(degree_index + 4) % 7]) % 12,
        }
        names = exact_chord_names_for_pitch_classes(triad, bass=root)
        if names:
            labels.append(names[0])
        seventh = {
            *triad,
            (candidate.root + intervals[(degree_index + 6) % 7]) % 12,
        }
        names = exact_chord_names_for_pitch_classes(seventh, bass=root)
        if names:
            labels.append(names[0])
    return labels


def _candidate_theory_fit(tones: set[int], analysis: TheoryAnalysis) -> float:
    if not tones or not analysis.candidates:
        return 0.0
    scale_tones = {
        (analysis.candidates[0].root + interval) % 12
        for interval in analysis.candidates[0].scale.intervals
    }
    return len(tones & scale_tones) / len(tones)


def _candidate_voice_leading(
    tones: set[int],
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
) -> float:
    scores = []
    for neighbor in [previous_chord, next_chord]:
        if neighbor is None:
            continue
        neighbor_tones = set(chord_pitch_classes_for_label(neighbor.label))
        if neighbor_tones:
            scores.append(_voice_leading_score(neighbor_tones, tones))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _voice_leading_score(from_tones: set[int], to_tones: set[int]) -> float:
    if not from_tones or not to_tones:
        return 0.0
    distances = []
    for pitch_class in from_tones:
        distances.append(min(_pitch_class_distance(pitch_class, target) for target in to_tones))
    average_distance = sum(distances) / len(distances)
    return fit_clamp(1.0 - average_distance / 6.0)


def _pitch_class_distance(first: int, second: int) -> int:
    distance = abs(first - second) % 12
    return min(distance, 12 - distance)


def _candidate_common_tones(
    tones: set[int],
    previous_chord: ChordRegion | None,
    next_chord: ChordRegion | None,
) -> float:
    scores = []
    for neighbor in [previous_chord, next_chord]:
        if neighbor is None:
            continue
        neighbor_tones = set(chord_pitch_classes_for_label(neighbor.label))
        if neighbor_tones:
            scores.append(len(tones & neighbor_tones) / len(tones | neighbor_tones))
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _previous_chord(chords: list[ChordRegion], seconds: float) -> ChordRegion | None:
    previous = [chord for chord in chords if chord.end <= seconds]
    return max(previous, key=lambda chord: chord.end, default=None)


def _next_chord(chords: list[ChordRegion], seconds: float) -> ChordRegion | None:
    next_chords = [chord for chord in chords if chord.start >= seconds]
    return min(next_chords, key=lambda chord: chord.start, default=None)


def _region_energy(notes: list[NoteEvent], start: float, end: float) -> float:
    total = 0.0
    for note in notes:
        overlap = max(0.0, min(note.end, end) - max(note.start, start))
        if overlap > 0:
            total += overlap * midi_velocity_energy(note.velocity)
    return total


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


def _report_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes:02d}:{remainder:06.3f}"
