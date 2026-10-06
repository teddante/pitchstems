from __future__ import annotations

from pitchstems.chord_gap_analysis import ChordGapAnalysis
from pitchstems.chord_analysis import analyze_chord_at, analyze_chord_region, analyze_chord_regions
from pitchstems.editor_models import NoteEvent
from pitchstems.review_ranges import (
    review_range_text,
    review_ranges,
    review_ranges_detail_text,
    single_review_range,
)
from pitchstems import gui_harmony_flow
from pitchstems.midi_energy import active_notes_at, midi_velocity_energy, note_overlap_seconds
from pitchstems.scale_analysis import TheoryAnalysis
from pitchstems.notation import pitch_class_for_name
from pitchstems.time_format import format_time


def current_chord_analysis_report(window) -> str:
    inputs = gui_harmony_flow.chord_inputs(window, window.timeline.position)
    source_notes = inputs.source_notes
    window.current_chord_base_weights = inputs.base_weights
    analysis_notes = inputs.analysis_notes
    required, excluded = inputs.required, inputs.excluded
    scoring_options = window.chord_scoring_options()
    explicit_ranges = window.timeline.selection_ranges()
    selection_ranges = review_ranges(explicit_ranges, window.timeline.selected_chord)
    if selection_ranges:
        selection = single_review_range(selection_ranges)
        if selection is not None:
            start, end = selection
            analysis = analyze_chord_region(
                analysis_notes,
                start,
                end,
                required_pitch_classes=required,
                excluded_pitch_classes=excluded,
                scoring_options=scoring_options,
            )
            label = (
                "Selected chord"
                if not explicit_ranges and window.timeline.selected_chord is not None
                else "Selection"
            )
            mode = f"{label} {review_range_text(selection)} ({end - start:.3f} sec)"
            evidence_rows, totals = chord_selection_evidence_rows(window, analysis_notes, start, end)
        else:
            analysis = analyze_chord_regions(
                analysis_notes,
                selection_ranges,
                required_pitch_classes=required,
                excluded_pitch_classes=excluded,
                scoring_options=scoring_options,
            )
            mode = f"Selection {review_ranges_detail_text(selection_ranges)}"
            evidence_rows, totals = chord_selection_ranges_evidence_rows(window, analysis_notes, selection_ranges)
    else:
        seconds = window.timeline.position
        analysis = analyze_chord_at(
            analysis_notes,
            seconds,
            required_pitch_classes=required,
            excluded_pitch_classes=excluded,
            scoring_options=scoring_options,
        )
        mode = f"Playhead {format_time(seconds)}"
        evidence_rows, totals = chord_point_evidence_rows(window, analysis_notes, seconds)

    lines = [
        "Harmony Inspector Calculation",
        "=" * 29,
        f"Context: {mode}",
        f"Detected chord: {window.display_chord(analysis.label)} (ranking score {analysis.confidence:.0%})",
        f"Sampled tracks: {', '.join(window.chord_analysis_track_names()) or '-'}",
        f"Source MIDI notes in sampled tracks: {len(source_notes):,}",
        f"Filtered/analyzed note events: {len(analysis_notes):,}",
        "",
        "MIDI Energy Evidence",
        "-" * 17,
        "MIDI energy model: note energy = overlap_seconds * (velocity / 127)^2",
        "Octaves and tracks: every note event contributes separately, then totals are folded by note name.",
        "Low-energy notes are kept unless the minimum note evidence slider or Manual Note Overrides remove them from naming.",
        (
            f"Minimum note evidence: {window.min_note_evidence_slider.value()}% normalized. "
            "Raw totals below this remain visible here but are ignored for chord naming."
        ),
        "",
        "Chord-Name Ranking",
        "-" * 18,
        "The visible percentage is a local ranking score, not a statistical probability.",
        "Display score = coverage * purity, using the MIDI evidence already shown above.",
        "Coverage asks how strongly the candidate's expected notes are present.",
        "Purity asks how much of the selected energy belongs to the candidate's notes.",
        "Automatic chord names that require a tone below visible evidence resolution are rejected.",
        "Forced notes constrain chord names without inventing MIDI energy.",
        "No naming bonuses, penalties, or user-tuned weights are applied.",
        "",
        "Manual Note Evidence Overrides",
        "-" * 30,
        f"Forced notes: {pitch_class_list(window, required)}",
        f"Excluded notes: {pitch_class_list(window, excluded)}",
        "",
        "Weighted Pitch-Class Totals",
        "-" * 27,
    ]
    if totals:
        max_total = max(totals.values())
        for pitch_class, total in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
            lines.append(
                f"{window.display_pitch_class_name(pitch_class):>2}: raw {total:.4f}, "
                f"normalized {total / max_total:.0%}"
            )
    else:
        lines.append("-")
    if analysis.note_weights:
        lines.extend(["", "Pitch Classes Used By Detector", "-" * 30])
        for name, weight in analysis.note_weights:
            pitch_class = pitch_class_for_name(name)
            shown_name = window.display_pitch_class_name(pitch_class) if pitch_class is not None else name
            lines.append(f"{shown_name:>2}: {weight:.0%}")

    lines.extend(["", "Input Note Events", "-" * 17])
    if evidence_rows:
        lines.extend(evidence_rows[:400])
        if len(evidence_rows) > 400:
            lines.append(f"... {len(evidence_rows) - 400} more note events")
    else:
        lines.append("-")

    lines.extend(["", "Chord Candidates And Formula Breakdown", "-" * 39])
    if analysis.candidates:
        for label, confidence in analysis.candidates:
            notes = " - ".join(window.display_chord_tones(label)) or "-"
            aliases = ", ".join(window.display_chord(alias) for alias in analysis.candidate_aliases.get(label, [])) or "-"
            lines.extend(
                [
                    "",
                    f"{window.display_chord(label)} ({confidence:.0%})",
                    f"Official tones: {notes}",
                    f"Alternate names: {aliases}",
                ]
            )
            lines.extend(analysis.candidate_explanations.get(label, ["No explanation available."]))
    else:
        lines.append("No full chord candidates here.")
    if analysis.partial_candidates:
        lines.extend(["", "Partial Chord Candidates", "-" * 24])
        for label, confidence in analysis.partial_candidates:
            notes = " - ".join(window.display_chord_tones(label)) or "-"
            aliases = (
                ", ".join(window.display_chord(alias) for alias in analysis.partial_candidate_aliases.get(label, []))
                or "-"
            )
            lines.extend(
                [
                    "",
                    f"{window.display_chord(label)} ({confidence:.0%})",
                    f"Observed tones: {notes}",
                    f"Alternate names: {aliases}",
                ]
            )
            lines.extend(analysis.partial_candidate_explanations.get(label, ["No explanation available."]))
    if analysis.partial_hints:
        lines.extend(["", "Partial Harmony Hints", "-" * 21])
        lines.extend(analysis.partial_hints)
    return "\n".join(lines)


def chord_selection_evidence_rows(
    window,
    notes: list[NoteEvent],
    start: float,
    end: float,
) -> tuple[list[str], dict[int, float]]:
    rows: list[str] = []
    totals: dict[int, float] = {}
    for note in sorted(notes, key=lambda item: (item.stem, item.start, item.pitch)):
        overlap = note_overlap_seconds(note, start, end)
        if overlap <= 0:
            continue
        velocity_energy = midi_velocity_energy(note.velocity)
        weight = overlap * velocity_energy
        totals[note.pitch % 12] = totals.get(note.pitch % 12, 0.0) + weight
        rows.append(
            f"{note.stem:12} {window.display_note_name(note.pitch):4} pitch {note.pitch:3} "
            f"start {format_time(note.start)} end {format_time(note.end)} "
            f"overlap {overlap:.3f}s velocity {note.velocity:3} "
            f"velocity energy {velocity_energy:.4f} note energy {weight:.4f}"
        )
    return rows, totals


def chord_selection_ranges_evidence_rows(
    window,
    notes: list[NoteEvent],
    ranges: list[tuple[float, float]],
) -> tuple[list[str], dict[int, float]]:
    rows: list[str] = []
    totals: dict[int, float] = {}
    for range_index, (start, end) in enumerate(ranges, start=1):
        range_rows, range_totals = chord_selection_evidence_rows(window, notes, start, end)
        rows.extend(f"range {range_index}: {row}" for row in range_rows)
        for pitch_class, total in range_totals.items():
            totals[pitch_class] = totals.get(pitch_class, 0.0) + total
    return rows, totals


def chord_point_evidence_rows(
    window,
    notes: list[NoteEvent],
    seconds: float,
) -> tuple[list[str], dict[int, float]]:
    rows: list[str] = []
    totals: dict[int, float] = {}
    for note in sorted(active_notes_at(notes, seconds), key=lambda item: (item.stem, item.pitch, item.start)):
        weight = midi_velocity_energy(note.velocity)
        totals[note.pitch % 12] = totals.get(note.pitch % 12, 0.0) + weight
        rows.append(
            f"{note.stem:12} {window.display_note_name(note.pitch):4} pitch {note.pitch:3} "
            f"start {format_time(note.start)} end {format_time(note.end)} "
            f"active at playhead velocity {note.velocity:3} velocity energy {weight:.4f}"
        )
    return rows, totals


def pitch_class_list(window, pitch_classes: set[int]) -> str:
    if not pitch_classes:
        return "-"
    return ", ".join(window.display_pitch_class_name(pitch_class) for pitch_class in sorted(pitch_classes))


def theory_analysis_report(analysis: TheoryAnalysis) -> str:
    detected = analysis.label or "No clear key/mode"
    score_label = "ranking score" if analysis.label else "best candidate score"
    lines = [
        "Theory Inspector Calculation",
        "============================",
        f"Detected interpretation: {detected} ({score_label} {analysis.confidence:.0%})",
        "",
        "Pitch Evidence",
        "--------------",
        "MIDI energy model: note energy = overlap_seconds * (velocity / 127)^2.",
        "Pitch classes are summed across octaves and selected analysis tracks.",
        "Pitch fit means the observed energy fits the scale; interpretation strength also needs enough coverage and tonal-centre evidence.",
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
                f"Evidence coverage: {candidate.evidence_strength:.0%}",
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


def chord_gap_report(analysis: ChordGapAnalysis) -> str:
    lines = [
        "Chord Gap Suggestions",
        "=====================",
        f"Gap: {format_time(analysis.start)} - {format_time(analysis.end)}",
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
