from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

from mido import MidiFile, tick2second

from pitchstems.pipeline import PipelineResult


DEFAULT_TEMPO = 500000
PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class NoteEvent:
    stem: str
    start: float
    end: float
    pitch: int
    velocity: int

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def name(self) -> str:
        return midi_note_name(self.pitch)


@dataclass(frozen=True)
class EditorTrack:
    name: str
    audio_path: Path
    muted: bool = False
    solo: bool = False


@dataclass(frozen=True)
class ChordRegion:
    start: float
    end: float
    label: str
    confidence: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


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
    candidate_explanations: dict[str, list[str]] = field(default_factory=dict)
    note_weights: list[tuple[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class EditorProject:
    project_dir: Path
    source_audio: Path
    tracks: list[EditorTrack]
    notes: list[NoteEvent]
    chords: list[ChordRegion]
    duration: float


def build_editor_project(result: PipelineResult) -> EditorProject:
    """Build the first editable timeline model from a completed pipeline result."""
    tracks = [EditorTrack(name=stem.name, audio_path=stem.path) for stem in result.stems]
    notes: list[NoteEvent] = []
    for midi in result.midi_files:
        notes.extend(read_midi_notes(midi.path, midi.stem))
    notes.sort(key=lambda note: (note.start, note.stem, note.pitch, note.end))
    duration = max(
        [note.end for note in notes]
        + [0.0]
    )
    chords = detect_chords(notes)
    return EditorProject(
        project_dir=result.project_dir,
        source_audio=result.normalized_audio,
        tracks=tracks,
        notes=notes,
        chords=chords,
        duration=duration,
    )


def read_midi_notes(path: Path, stem: str) -> list[NoteEvent]:
    """Read note on/off events from a MIDI file into absolute seconds."""
    midi = MidiFile(path)
    notes: list[NoteEvent] = []

    for track in midi.tracks:
        tempo = DEFAULT_TEMPO
        seconds = 0.0
        active: dict[int, list[tuple[float, int]]] = {}
        for message in track:
            seconds += tick2second(message.time, midi.ticks_per_beat, tempo)
            if message.type == "set_tempo":
                tempo = message.tempo
                continue
            if message.type == "note_on" and message.velocity > 0:
                active.setdefault(message.note, []).append((seconds, message.velocity))
                continue
            if message.type in {"note_off", "note_on"}:
                starts = active.get(message.note)
                if not starts:
                    continue
                start, velocity = starts.pop(0)
                if seconds > start:
                    notes.append(
                        NoteEvent(
                            stem=stem,
                            start=start,
                            end=seconds,
                            pitch=message.note,
                            velocity=velocity,
                        )
                    )
    return notes


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
    regions: list[ChordRegion] = []
    active: list[NoteEvent] = []
    for start, end in zip(times, times[1:]):
        for note in ends.get(start, []):
            with contextlib.suppress(ValueError):
                active.remove(note)
        active.extend(starts.get(start, []))
        if end - start < minimum_region:
            continue
        analysis = analyze_chord([note.pitch for note in active])
        if not analysis.label:
            continue
        if regions and regions[-1].label == analysis.label and abs(regions[-1].end - start) < 0.05:
            previous = regions[-1]
            regions[-1] = ChordRegion(
                start=previous.start,
                end=end,
                label=previous.label,
                confidence=max(previous.confidence, analysis.confidence),
            )
        else:
            regions.append(
                ChordRegion(
                    start=start,
                    end=end,
                    label=analysis.label,
                    confidence=analysis.confidence,
                )
            )
    return regions


def active_notes_at(notes: list[NoteEvent], seconds: float) -> list[NoteEvent]:
    return sorted(
        [note for note in notes if note.start <= seconds < note.end],
        key=lambda note: (note.pitch, note.stem),
    )


def analyze_chord_at(notes: list[NoteEvent], seconds: float) -> ChordAnalysis:
    return analyze_chord([note.pitch for note in active_notes_at(notes, seconds)])


def analyze_chord_region(notes: list[NoteEvent], start: float, end: float) -> ChordAnalysis:
    start, end = sorted((start, end))
    if end - start <= 0:
        return ChordAnalysis(None, 0.0, [], [])

    pitch_weights: dict[int, float] = {}
    exact_pitch_weights: dict[int, float] = {}
    for note in notes:
        overlap = max(0.0, min(note.end, end) - max(note.start, start))
        if overlap <= 0:
            continue
        velocity_factor = 0.35 + 0.65 * (max(1, min(note.velocity, 127)) / 127)
        weight = overlap * velocity_factor
        pitch_weights[note.pitch % 12] = pitch_weights.get(note.pitch % 12, 0.0) + weight
        exact_pitch_weights[note.pitch] = exact_pitch_weights.get(note.pitch, 0.0) + weight

    if len(pitch_weights) < 3:
        active_note_names = [midi_note_name(pitch) for pitch in sorted(exact_pitch_weights)]
        return ChordAnalysis(None, 0.0, active_note_names, sorted(pitch_weights))

    max_exact_weight = max(exact_pitch_weights.values())
    bass_pitch = min(
        pitch
        for pitch, weight in exact_pitch_weights.items()
        if weight >= max_exact_weight * 0.12
    )
    active_note_names = [midi_note_name(pitch) for pitch in sorted(exact_pitch_weights)]
    max_pitch_class_weight = max(pitch_weights.values())
    note_weights = [
        (PITCH_NAMES[pitch_class], weight / max_pitch_class_weight)
        for pitch_class, weight in sorted(
            pitch_weights.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return _analyze_weighted_pitch_classes(pitch_weights, bass_pitch % 12, active_note_names, note_weights)


def analyze_chord(pitches: list[int]) -> ChordAnalysis:
    active_note_names = [midi_note_name(pitch) for pitch in sorted(set(pitches))]
    pitch_classes = sorted({pitch % 12 for pitch in pitches})
    if len(pitch_classes) < 3:
        return ChordAnalysis(None, 0.0, active_note_names, pitch_classes)

    bass = min(pitches) % 12
    scored_roots: list[tuple[str, float, int, list[str]]] = []
    for root in range(12):
        label, score, explanation = _score_root(root, set(pitch_classes), bass)
        scored_roots.append((label, score, root, explanation))

    scored_roots.sort(key=lambda item: item[1], reverse=True)
    best_label, best_score, best_root, _best_explanation = scored_roots[0]
    candidates = [
        (label, score)
        for label, score, _root, _explanation in scored_roots
        if score >= 0.72 and score >= best_score - 0.18
    ][:6]
    candidate_notes = {
        label: chord_tones_for_label(label)
        for label, _score in candidates
    }
    candidate_explanations = {
        label: explanation
        for label, score, _root, explanation in scored_roots
        if (label, score) in candidates
    }

    if best_label is None or best_score < 0.72:
        return ChordAnalysis(None, best_score, active_note_names, pitch_classes, best_root, bass)
    return ChordAnalysis(
        best_label,
        best_score,
        active_note_names,
        pitch_classes,
        best_root,
        bass,
        candidates,
        candidate_notes,
        candidate_explanations,
    )


def _analyze_weighted_pitch_classes(
    pitch_weights: dict[int, float],
    bass: int,
    active_note_names: list[str],
    note_weights: list[tuple[str, float]],
) -> ChordAnalysis:
    pitch_classes = sorted(pitch_weights)
    scored_roots = [
        (*_score_weighted_root(root, pitch_weights, bass), root)
        for root in range(12)
    ]
    scored_roots.sort(key=lambda item: item[1], reverse=True)
    best_label, best_score, _best_explanation, best_root = scored_roots[0]
    candidates = [
        (label, score)
        for label, score, _explanation, _root in scored_roots
        if score >= 0.58 and score >= best_score - 0.22
    ][:6]
    candidate_notes = {
        label: chord_tones_for_label(label)
        for label, _score in candidates
    }
    candidate_explanations = {
        label: explanation
        for label, score, explanation, _root in scored_roots
        if (label, score) in candidates
    }
    if best_score < 0.58:
        return ChordAnalysis(
            None,
            best_score,
            active_note_names,
            pitch_classes,
            best_root,
            bass,
            candidates,
            candidate_notes,
            candidate_explanations,
            note_weights,
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
        candidate_explanations,
        note_weights,
    )


def identify_chord(pitches: list[int]) -> tuple[str | None, float]:
    analysis = analyze_chord(pitches)
    return analysis.label, analysis.confidence


def midi_note_name(pitch: int) -> str:
    octave = (pitch // 12) - 1
    return f"{PITCH_NAMES[pitch % 12]}{octave}"


def chord_tones_for_label(label: str) -> list[str]:
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
        return []
    suffix = base_label[len(root_name):]
    quality = next(
        (
            intervals
            for quality_suffix, intervals in _chord_qualities()
            if quality_suffix == suffix
        ),
        None,
    )
    if quality is None:
        return []
    root = PITCH_NAMES.index(root_name)
    return [PITCH_NAMES[(root + interval) % 12] for interval in quality]


def _score_root(root: int, pitch_classes: set[int], bass: int) -> tuple[str, float, list[str]]:
    intervals = {(pitch - root) % 12 for pitch in pitch_classes}
    qualities = _chord_qualities()
    root_bonus = 0.12 if bass == root else 0.04 if root in pitch_classes else 0.0
    best_quality = ""
    best_score = 0.0
    best_explanation: list[str] = []
    for suffix, required in qualities:
        required_set = set(required)
        matched = len(intervals & required_set)
        extras = len(intervals - required_set)
        missing = len(required_set - intervals)
        exact_bonus = 0.18 if intervals == required_set else 0.0
        score = (
            (matched / len(required_set))
            - (extras * 0.10)
            - (missing * 0.22)
            + root_bonus
            + exact_bonus
        )
        if score > best_score:
            best_quality = suffix
            best_score = score
            label = f"{PITCH_NAMES[root]}{suffix}"
            if bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            best_explanation = _plain_score_explanation(
                label=label,
                root=root,
                required=required,
                intervals=intervals,
                bass=bass,
                root_bonus=root_bonus,
                exact_bonus=exact_bonus,
                matched=matched,
                extras=extras,
                missing=missing,
                score=score,
            )
    label = f"{PITCH_NAMES[root]}{best_quality}"
    if bass != root:
        label = f"{label}/{PITCH_NAMES[bass]}"
    return label, max(0.0, min(1.0, best_score)), best_explanation


def _score_weighted_root(root: int, pitch_weights: dict[int, float], bass: int) -> tuple[str, float, list[str]]:
    interval_weights = {
        (pitch - root) % 12: weight
        for pitch, weight in pitch_weights.items()
    }
    total_weight = max(0.0001, sum(interval_weights.values()))
    max_weight = max(interval_weights.values())
    root_bonus = 0.12 if bass == root else 0.04 if root in pitch_weights else 0.0
    best_quality = ""
    best_score = 0.0
    best_explanation: list[str] = []
    for suffix, required in _chord_qualities():
        required_set = set(required)
        required_weight = sum(interval_weights.get(interval, 0.0) for interval in required) / total_weight
        extra_weight = sum(
            weight
            for interval, weight in interval_weights.items()
            if interval not in required_set
        ) / total_weight
        missing = sum(1 for interval in required_set if interval not in interval_weights)
        presence = sum(
            min(1.0, interval_weights.get(interval, 0.0) / max_weight)
            for interval in required
        ) / len(required)
        exact_bonus = 0.10 if extra_weight < 0.04 and missing == 0 else 0.0
        complexity_penalty = max(0, len(required) - 3) * 0.025
        score = (
            required_weight * 0.62
            + presence * 0.32
            - extra_weight * 0.16
            - missing * 0.18
            + root_bonus
            + exact_bonus
            - complexity_penalty
        )
        if score > best_score:
            best_quality = suffix
            best_score = score
            label = f"{PITCH_NAMES[root]}{suffix}"
            if bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            best_explanation = _weighted_score_explanation(
                label=label,
                root=root,
                required=required,
                interval_weights=interval_weights,
                bass=bass,
                root_bonus=root_bonus,
                required_weight=required_weight,
                extra_weight=extra_weight,
                missing=missing,
                presence=presence,
                exact_bonus=exact_bonus,
                complexity_penalty=complexity_penalty,
                score=score,
            )
    label = f"{PITCH_NAMES[root]}{best_quality}"
    if bass != root:
        label = f"{label}/{PITCH_NAMES[bass]}"
    return label, max(0.0, min(1.0, best_score)), best_explanation


def _plain_score_explanation(
    label: str,
    root: int,
    required: tuple[int, ...],
    intervals: set[int],
    bass: int,
    root_bonus: float,
    exact_bonus: float,
    matched: int,
    extras: int,
    missing: int,
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
        f"Bass evidence: {PITCH_NAMES[bass]} gives +{root_bonus:.2f}. Exact-match bonus: +{exact_bonus:.2f}.",
        "Formula: matched/required - 0.10*extras - 0.22*missing + bass/root bonus + exact-match bonus.",
        f"Raw score {score:.2f}, displayed confidence {max(0.0, min(1.0, score)):.0%}.",
    ]


def _weighted_score_explanation(
    label: str,
    root: int,
    required: tuple[int, ...],
    interval_weights: dict[int, float],
    bass: int,
    root_bonus: float,
    required_weight: float,
    extra_weight: float,
    missing: int,
    presence: float,
    exact_bonus: float,
    complexity_penalty: float,
    score: float,
) -> list[str]:
    required_set = set(required)
    matched_notes = [
        f"{PITCH_NAMES[(root + interval) % 12]} {interval_weights[interval] / sum(interval_weights.values()):.0%}"
        for interval in required
        if interval in interval_weights
    ]
    missing_notes = _interval_names(root, sorted(required_set - set(interval_weights)))
    extra_notes = [
        f"{PITCH_NAMES[(root + interval) % 12]} {weight / sum(interval_weights.values()):.0%}"
        for interval, weight in sorted(interval_weights.items())
        if interval not in required_set
    ]
    return [
        f"{label}: scored from weighted notes across the selected time range.",
        f"Chord tones expected: {' - '.join(_interval_names(root, required))}.",
        f"Matched weighted tones: {', '.join(matched_notes) or 'none'}; required-tone weight {required_weight:.0%}.",
        f"Missing tones: {', '.join(missing_notes) or 'none'}. Extra weighted tones: {', '.join(extra_notes) or 'none'} ({extra_weight:.0%}).",
        f"Presence balance: {presence:.0%}. Bass evidence: {PITCH_NAMES[bass]} gives +{root_bonus:.2f}.",
        f"Bonuses/penalties: exact +{exact_bonus:.2f}, complexity -{complexity_penalty:.2f}, missing -{missing * 0.18:.2f}.",
        "Formula: 0.62*required-weight + 0.32*presence - 0.16*extra-weight - 0.18*missing + bass/root bonus + exact bonus - complexity penalty.",
        f"Raw score {score:.2f}, displayed confidence {max(0.0, min(1.0, score)):.0%}.",
    ]


def _interval_names(root: int, intervals) -> list[str]:
    return [PITCH_NAMES[(root + interval) % 12] for interval in intervals]


def _chord_qualities() -> list[tuple[str, tuple[int, ...]]]:
    return [
        ("maj9", (0, 4, 7, 11, 2)),
        ("9", (0, 4, 7, 10, 2)),
        ("m9", (0, 3, 7, 10, 2)),
        ("maj7", (0, 4, 7, 11)),
        ("7", (0, 4, 7, 10)),
        ("m7", (0, 3, 7, 10)),
        ("mMaj7", (0, 3, 7, 11)),
        ("m7b5", (0, 3, 6, 10)),
        ("dim7", (0, 3, 6, 9)),
        ("6", (0, 4, 7, 9)),
        ("m6", (0, 3, 7, 9)),
        ("add9", (0, 4, 7, 2)),
        ("madd9", (0, 3, 7, 2)),
        ("7sus4", (0, 5, 7, 10)),
        ("sus2", (0, 2, 7)),
        ("sus4", (0, 5, 7)),
        ("dim", (0, 3, 6)),
        ("aug", (0, 4, 8)),
        ("m", (0, 3, 7)),
        ("", (0, 4, 7)),
    ]
