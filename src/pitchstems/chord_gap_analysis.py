from __future__ import annotations

from dataclasses import dataclass, field

from pitchstems.chord_analysis import ChordAnalysis, chord_pitch_classes_for_label
from pitchstems.chord_detection import analyze_chord_region
from pitchstems.chord_scoring import ChordScoringOptions
from pitchstems.editor_models import ChordRegion, NoteEvent
from pitchstems.scale_analysis import TheoryAnalysis, analyze_theory_region
from pitchstems.theory_helpers import (
    candidate_common_tones,
    candidate_pitch_class_movement,
    candidate_theory_fit,
    diatonic_chord_labels,
    fit_clamp,
    next_chord as find_next_chord,
    previous_chord as find_previous_chord,
    region_energy,
    report_time,
)

@dataclass(frozen=True)
class ChordGapSuggestion:
    label: str
    score: float
    action: str
    start: float
    end: float
    local_evidence: float
    theory_fit: float
    pitch_class_movement: float
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


def analyze_chord_gap(
    notes: list[NoteEvent],
    chords: list[ChordRegion],
    start: float,
    end: float,
    scoring_options: ChordScoringOptions | None = None,
) -> ChordGapAnalysis:
    start, end = sorted((start, end))
    previous_chord = find_previous_chord(chords, start)
    next_chord = find_next_chord(chords, end)
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
        f"Gap: {report_time(analysis.start)} - {report_time(analysis.end)}",
        f"Previous chord: {analysis.previous_chord.label if analysis.previous_chord else '-'}",
        f"Next chord: {analysis.next_chord.label if analysis.next_chord else '-'}",
        "",
        "Evidence Model",
        "--------------",
        "Local MIDI evidence uses the same overlap_seconds * (velocity / 127)^2 energy model.",
        "Theory fit checks formal chord tones against the current scale/key/mode candidate.",
        "Pitch-class movement uses minimum distance on the 12-tone circle; it does not model register-aware part-writing.",
        "Common-tone support counts shared pitch classes with neighbouring chord regions.",
        "Suggestions are ordered by evidence-first ranking rules, not blended policy weights.",
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
                f"Pitch-class movement: {suggestion.pitch_class_movement:.0%}",
                f"Common-tone support: {suggestion.common_tone_support:.0%}",
                *suggestion.explanation,
            ]
        )
    return "\n".join(lines)


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
    for label in diatonic_chord_labels(theory_analysis):
        candidates.setdefault(label, ("insert", 0.0))

    suggestions = []
    gap_note_energy = region_energy(notes, start, end)
    no_local_evidence = 1.0 if gap_note_energy <= 0 else 0.0
    local_scores = dict(local_chord_analysis.candidates)
    for label, (action, generated_local_score) in candidates.items():
        tones = set(chord_pitch_classes_for_label(label))
        if not tones:
            continue
        local_evidence = max(generated_local_score, local_scores.get(label, 0.0))
        if action in {"extend_previous", "start_next"}:
            local_evidence = max(local_evidence, no_local_evidence)
        theory_fit = candidate_theory_fit(tones, theory_analysis)
        pitch_class_movement = candidate_pitch_class_movement(tones, previous_chord, next_chord)
        common_tone_support = candidate_common_tones(tones, previous_chord, next_chord)
        score = _gap_display_strength(action, local_evidence, theory_fit, no_local_evidence)
        suggestions.append(
            ChordGapSuggestion(
                label=label,
                score=fit_clamp(score),
                action=action,
                start=start,
                end=end,
                local_evidence=fit_clamp(local_evidence),
                theory_fit=fit_clamp(theory_fit),
                pitch_class_movement=fit_clamp(pitch_class_movement),
                common_tone_support=fit_clamp(common_tone_support),
                explanation=[
                    f"{label} is ranked from local MIDI evidence, formal scale/key fit, "
                    "pitch-class movement, and common tones with neighbour chords.",
                    "Ranking rule: if the gap has MIDI evidence, local chord evidence is primary; "
                    "if it has no MIDI evidence, continuity actions are primary. Formal theory fit, "
                    "pitch-class movement, and common tones are deterministic tie-breakers.",
                ],
            )
        )
    suggestions.sort(
        key=lambda suggestion: _gap_suggestion_sort_key(suggestion, no_local_evidence > 0),
        reverse=True,
    )
    return suggestions[:10]


def _gap_display_strength(
    action: str,
    local_evidence: float,
    theory_fit: float,
    no_local_evidence: float,
) -> float:
    if action in {"extend_previous", "start_next"} and no_local_evidence:
        return 1.0
    if local_evidence > 0:
        return local_evidence
    return theory_fit


def _gap_suggestion_sort_key(
    suggestion: ChordGapSuggestion,
    gap_has_no_local_evidence: bool,
) -> tuple[float, ...]:
    is_continuity = suggestion.action in {"extend_previous", "start_next"}
    has_local_chord_evidence = suggestion.local_evidence > 0 and not (
        is_continuity and gap_has_no_local_evidence
    )
    if gap_has_no_local_evidence:
        return (
            float(is_continuity),
            suggestion.theory_fit,
            suggestion.pitch_class_movement,
            suggestion.common_tone_support,
        )
    return (
        float(has_local_chord_evidence),
        suggestion.local_evidence,
        suggestion.theory_fit,
        suggestion.pitch_class_movement,
        suggestion.common_tone_support,
    )
