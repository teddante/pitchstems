from __future__ import annotations

from dataclasses import dataclass


SHARP_PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLAT_PITCH_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
DEFAULT_PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
LETTERS = ("C", "D", "E", "F", "G", "A", "B")
NATURAL_PITCH_CLASSES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_NAME_TO_PITCH_CLASS = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}


@dataclass(frozen=True)
class ChordLabelParts:
    root_name: str
    root_pitch_class: int
    suffix: str
    bass_name: str | None = None
    bass_pitch_class: int | None = None


def normalize_spelling_preference(preference: str | None) -> str:
    if preference in {"sharp", "flat"}:
        return preference
    return "auto"


def pitch_class_for_name(note_name: str) -> int | None:
    token = _note_token(note_name)
    return NOTE_NAME_TO_PITCH_CLASS.get(token)


def pitch_class_name(pitch_class: int, preference: str | None = "auto") -> str:
    preference = normalize_spelling_preference(preference)
    pitch_class %= 12
    if preference == "sharp":
        return SHARP_PITCH_NAMES[pitch_class]
    if preference == "flat":
        return FLAT_PITCH_NAMES[pitch_class]
    return DEFAULT_PITCH_NAMES[pitch_class]


def midi_note_name(pitch: int, preference: str | None = "auto") -> str:
    octave = pitch // 12 - 1
    return f"{pitch_class_name(pitch, preference)}{octave}"


def normalized_pitch_class_weights(totals: dict[int, float]) -> list[tuple[str, float]]:
    max_total = max(totals.values(), default=0.0)
    if max_total <= 0:
        return []
    return [
        (DEFAULT_PITCH_NAMES[pitch_class], weight / max_total)
        for pitch_class, weight in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def split_chord_label(label: str) -> ChordLabelParts | None:
    base_label, slash, bass_label = label.partition("/")
    root = _leading_note_name(base_label)
    if root is None:
        return None
    root_pc = NOTE_NAME_TO_PITCH_CLASS[root]
    bass_name = None
    bass_pc = None
    if slash:
        bass = _leading_note_name(bass_label)
        if bass is not None:
            bass_name = bass
            bass_pc = NOTE_NAME_TO_PITCH_CLASS[bass]
    return ChordLabelParts(
        root_name=root,
        root_pitch_class=root_pc,
        suffix=base_label[len(root):],
        bass_name=bass_name,
        bass_pitch_class=bass_pc,
    )


def respell_chord_label(label: str, preference: str | None = "auto") -> str:
    parts = split_chord_label(label)
    if parts is None:
        return label
    resolved = _resolve_preference(preference, parts.root_name)
    root_name = pitch_class_name(parts.root_pitch_class, resolved)
    if parts.bass_pitch_class is None:
        return f"{root_name}{parts.suffix}"
    bass_name = pitch_class_name(parts.bass_pitch_class, resolved)
    return f"{root_name}{parts.suffix}/{bass_name}"


def spell_chord_tones(
    label: str,
    intervals: list[int] | tuple[int, ...],
    preference: str | None = "auto",
) -> list[str]:
    parts = split_chord_label(label)
    if parts is None:
        return [pitch_class_name(interval, preference) for interval in intervals]
    resolved = _resolve_preference(preference, parts.root_name)
    root_name = pitch_class_name(parts.root_pitch_class, resolved)
    return [
        _spell_interval_from_root(root_name, (parts.root_pitch_class + interval) % 12, interval)
        for interval in intervals
    ]


def spell_scale(
    root_pitch_class: int,
    intervals: tuple[int, ...],
    preference: str | None = "auto",
) -> list[str]:
    root_name = scale_root_name(root_pitch_class, intervals, preference)
    if len(intervals) != 7:
        resolved = _resolve_preference(preference, root_name)
        return [pitch_class_name(root_pitch_class + interval, resolved) for interval in intervals]
    return [
        _spell_scale_degree(root_name, (root_pitch_class + interval) % 12, degree_index)
        for degree_index, interval in enumerate(intervals)
    ]


def scale_label(
    root_pitch_class: int,
    intervals: tuple[int, ...],
    scale_name: str,
    preference: str | None = "auto",
) -> str:
    root_name = scale_root_name(root_pitch_class, intervals, preference)
    if scale_name == "Ionian":
        return f"{root_name} major"
    if scale_name == "Aeolian":
        return f"{root_name} natural minor"
    return f"{root_name} {scale_name}"


def scale_root_name(
    root_pitch_class: int,
    intervals: tuple[int, ...],
    preference: str | None = "auto",
) -> str:
    preference = normalize_spelling_preference(preference)
    if preference != "auto":
        return pitch_class_name(root_pitch_class, preference)
    candidates = {
        pitch_class_name(root_pitch_class, "sharp"),
        pitch_class_name(root_pitch_class, "flat"),
        pitch_class_name(root_pitch_class, "auto"),
    }
    scored = []
    for root_name in candidates:
        notes = _spell_heptatonic_candidate(root_name, root_pitch_class, intervals)
        accidental_cost = sum(_accidental_cost(note) for note in notes)
        double_accidentals = sum(1 for note in notes if "bb" in note or "##" in note)
        flats = sum(note.count("b") for note in notes)
        sharps = sum(note.count("#") for note in notes)
        mixed = int(flats > 0 and sharps > 0)
        scored.append((double_accidentals, accidental_cost, mixed, abs(sharps - flats), root_name))
    scored.sort()
    return scored[0][-1]


def spelling_preference_from_label(label: str | None) -> str:
    if not label:
        return "auto"
    parts = split_chord_label(label)
    if parts is None:
        root = _leading_note_name(label)
        if root is None:
            return "auto"
    else:
        root = parts.root_name
    if "b" in root:
        return "flat"
    if "#" in root:
        return "sharp"
    return "auto"


def _resolve_preference(preference: str | None, root_name: str | None = None) -> str:
    preference = normalize_spelling_preference(preference)
    if preference != "auto":
        return preference
    if root_name:
        if "b" in root_name:
            return "flat"
        if "#" in root_name:
            return "sharp"
    return "auto"


def _leading_note_name(text: str) -> str | None:
    for length in (2, 1):
        token = text[:length]
        if token in NOTE_NAME_TO_PITCH_CLASS:
            return token
    return None


def _note_token(note_name: str) -> str:
    if len(note_name) >= 2 and note_name[1] in {"#", "b"}:
        return note_name[:2]
    return note_name[:1]


def _spell_interval_from_root(root_name: str, target_pitch_class: int, interval: int) -> str:
    root_letter = root_name[0]
    letter_steps = _chord_interval_letter_steps(interval)
    target_letter = LETTERS[(LETTERS.index(root_letter) + letter_steps) % len(LETTERS)]
    return _spell_pitch_for_letter(target_pitch_class, target_letter)


def _chord_interval_letter_steps(interval: int) -> int:
    return {
        0: 0,
        1: 1,
        2: 1,
        3: 2,
        4: 2,
        5: 3,
        6: 4,
        7: 4,
        8: 4,
        9: 5,
        10: 6,
        11: 6,
    }.get(interval % 12, 0)


def _spell_scale_degree(root_name: str, target_pitch_class: int, degree_index: int) -> str:
    root_letter = root_name[0]
    target_letter = LETTERS[(LETTERS.index(root_letter) + degree_index) % len(LETTERS)]
    return _spell_pitch_for_letter(target_pitch_class, target_letter)


def _spell_pitch_for_letter(target_pitch_class: int, letter: str) -> str:
    natural = NATURAL_PITCH_CLASSES[letter]
    diff = (target_pitch_class - natural) % 12
    if diff > 6:
        diff -= 12
    accidental = {
        -2: "bb",
        -1: "b",
        0: "",
        1: "#",
        2: "##",
    }.get(diff)
    if accidental is None:
        return pitch_class_name(target_pitch_class, "auto")
    return f"{letter}{accidental}"


def _spell_heptatonic_candidate(
    root_name: str,
    root_pitch_class: int,
    intervals: tuple[int, ...],
) -> list[str]:
    if len(intervals) != 7:
        return [pitch_class_name(root_pitch_class + interval, "auto") for interval in intervals]
    return [
        _spell_scale_degree(root_name, (root_pitch_class + interval) % 12, degree_index)
        for degree_index, interval in enumerate(intervals)
    ]


def _accidental_cost(note_name: str) -> int:
    return note_name.count("#") + note_name.count("b")
