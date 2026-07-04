from __future__ import annotations

from dataclasses import dataclass

from pitchstems.notation import (
    DEFAULT_PITCH_NAMES,
    LETTERS,
    pitch_class_name,
    respell_chord_label,
    spell_chord_tones,
    spell_pitch_for_letter,
    split_chord_label,
)

PITCH_NAMES = DEFAULT_PITCH_NAMES


@dataclass(frozen=True)
class ChordSymbol:
    root: int
    suffix: str
    intervals: tuple[int, ...]
    bass: int | None = None
    alterations: tuple[str, ...] = ()

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return tuple(_dedupe((self.root + interval) % 12 for interval in self.intervals))

    @property
    def sounding_pitch_classes(self) -> tuple[int, ...]:
        tones = list(self.pitch_classes)
        if self.bass is not None and self.bass in tones:
            tones.remove(self.bass)
            tones.insert(0, self.bass)
        elif self.bass is not None:
            tones.insert(0, self.bass)
        return tuple(tones)


def display_chord_label(label: str, spelling_preference: str | None = "auto") -> str:
    return respell_chord_label(label, spelling_preference)


def chord_bass_name_for_label(label: str, spelling_preference: str | None = "auto") -> str | None:
    parts = split_chord_label(label)
    if parts is None or parts.bass_pitch_class is None:
        return None
    return pitch_class_name(parts.bass_pitch_class, spelling_preference)


def chord_tones_for_label(label: str, spelling_preference: str | None = "auto") -> list[str]:
    symbol = parse_chord_symbol(label)
    if symbol is None:
        return [PITCH_NAMES[pitch_class] for pitch_class in chord_pitch_classes_for_label(label)]
    names = spell_chord_tones(label, symbol.intervals, spelling_preference)
    if symbol.alterations:
        return _respell_altered_tones(label, symbol, names)
    return names


def alternate_chord_names_for_label(label: str, bass: int | None = None) -> list[str]:
    pitch_classes = set(chord_pitch_classes_for_label(label))
    if not pitch_classes:
        return []
    return [
        alias
        for alias in exact_chord_names_for_pitch_classes(pitch_classes, bass)
        if alias != label
    ]


def exact_chord_names_for_pitch_classes(pitch_classes: set[int], bass: int | None = None) -> list[str]:
    names: list[str] = []
    for root in range(12):
        for suffix, intervals in _chord_qualities():
            tones = {(root + interval) % 12 for interval in intervals}
            if tones != pitch_classes:
                continue
            label = f"{PITCH_NAMES[root]}{suffix}"
            if bass is not None and bass != root:
                label = f"{label}/{PITCH_NAMES[bass]}"
            names.append(label)
    return names


def chord_quality_templates() -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(_chord_qualities())


def parse_chord_symbol(label: str) -> ChordSymbol | None:
    parts = split_chord_label(label)
    if parts is None:
        return None
    quality = _quality_details(parts.suffix)
    if quality is None:
        return None
    intervals, alterations = quality
    return ChordSymbol(
        root=parts.root_pitch_class,
        suffix=parts.suffix,
        intervals=intervals,
        bass=parts.bass_pitch_class,
        alterations=alterations,
    )


def chord_pitch_classes_for_label(label: str) -> list[int]:
    symbol = parse_chord_symbol(label)
    if symbol is None:
        return []
    return list(symbol.pitch_classes)


def chord_sounding_pitch_classes_for_label(label: str) -> list[int]:
    symbol = parse_chord_symbol(label)
    if symbol is None:
        return []
    return list(symbol.sounding_pitch_classes)


def _quality_details(suffix: str) -> tuple[tuple[int, ...], tuple[str, ...]] | None:
    omitted_intervals: set[int] = set()
    if "(no" in suffix:
        suffix, omitted_intervals = _split_omitted_suffix(suffix)
    quality = _base_quality_details(suffix)
    if quality is None:
        return None
    intervals, alterations = quality
    return tuple(
        interval
        for interval in intervals
        if interval not in omitted_intervals
    ), alterations


def _base_quality_details(suffix: str) -> tuple[tuple[int, ...], tuple[str, ...]] | None:
    quality = _exact_quality_intervals(suffix)
    if quality is not None:
        return quality, ()
    return _altered_quality_intervals(suffix)


def _exact_quality_intervals(suffix: str) -> tuple[int, ...] | None:
    return next(
        (
            intervals
            for quality_suffix, intervals in _chord_qualities()
            if quality_suffix == suffix
        ),
        None,
    )


def _dedupe(values) -> list[int]:
    tones: list[int] = []
    for interval in values:
        pitch_class = interval % 12
        if pitch_class not in tones:
            tones.append(pitch_class)
    return tones


def _altered_quality_intervals(suffix: str) -> tuple[tuple[int, ...], tuple[str, ...]] | None:
    for base_suffix, intervals in _alterable_quality_bases():
        if not suffix.startswith(base_suffix):
            continue
        alteration_text = suffix[len(base_suffix):]
        if not alteration_text:
            return intervals, ()
        alterations = _parse_alterations(alteration_text)
        if alterations is None:
            continue
        return _apply_alterations(intervals, alterations), alterations
    return None


def _parse_alterations(text: str) -> tuple[str, ...] | None:
    alterations: list[str] = []
    index = 0
    while index < len(text):
        accidental = text[index]
        if accidental not in {"b", "#"}:
            return None
        index += 1
        start = index
        while index < len(text) and text[index].isdigit():
            index += 1
        if start == index:
            return None
        token = f"{accidental}{text[start:index]}"
        if token not in _ALTERED_INTERVALS:
            return None
        alterations.append(token)
    return tuple(alterations)


def _apply_alterations(intervals: tuple[int, ...], alterations: tuple[str, ...]) -> tuple[int, ...]:
    result = list(intervals)
    for alteration in alterations:
        natural_interval = _ALTERATION_REPLACEMENTS[alteration]
        if natural_interval in {interval % 12 for interval in result}:
            result = _replace_interval(result, natural_interval, _ALTERED_INTERVALS[alteration])
        else:
            result.append(_ALTERED_INTERVALS[alteration])
    return tuple(_dedupe(result))


def _replace_interval(intervals: list[int], natural_interval: int, altered_interval: int) -> list[int]:
    return [
        altered_interval if interval % 12 == natural_interval else interval
        for interval in intervals
    ]


def _respell_altered_tones(label: str, symbol: ChordSymbol, names: list[str]) -> list[str]:
    parts = split_chord_label(label)
    if parts is None:
        return names
    spelled = list(names)
    root_letter = parts.root_name[0]
    for alteration in symbol.alterations:
        interval = _ALTERED_INTERVALS[alteration]
        try:
            index = next(
                tone_index
                for tone_index, tone_interval in enumerate(symbol.intervals)
                if tone_interval % 12 == interval
            )
        except StopIteration:
            continue
        target_letter = LETTERS[
            (LETTERS.index(root_letter) + _ALTERED_LETTER_STEPS[alteration]) % len(LETTERS)
        ]
        spelled[index] = spell_pitch_for_letter((symbol.root + interval) % 12, target_letter)
    return spelled


def _split_omitted_suffix(suffix: str) -> tuple[str, set[int]]:
    omitted_intervals: set[int] = set()
    base = suffix
    while "(no" in base:
        start = base.find("(no")
        end = base.find(")", start)
        if end < 0:
            break
        token = base[start + 3:end]
        if token == "3":
            omitted_intervals.update({3, 4})
        elif token == "5":
            omitted_intervals.add(7)
        base = f"{base[:start]}{base[end + 1:]}"
    return base, omitted_intervals


def _chord_qualities() -> list[tuple[str, tuple[int, ...]]]:
    return [
        ("maj13", (0, 4, 7, 11, 2, 9)),
        ("13", (0, 4, 7, 10, 2, 9)),
        ("m13", (0, 3, 7, 10, 2, 5, 9)),
        ("maj11", (0, 4, 7, 11, 2, 5)),
        ("11", (0, 4, 7, 10, 2, 5)),
        ("m11", (0, 3, 7, 10, 2, 5)),
        ("maj9(no3)", (0, 7, 11, 2)),
        ("9(no3)", (0, 7, 10, 2)),
        ("maj9", (0, 4, 7, 11, 2)),
        ("9", (0, 4, 7, 10, 2)),
        ("m9", (0, 3, 7, 10, 2)),
        ("maj7sus2", (0, 2, 7, 11)),
        ("7sus2", (0, 2, 7, 10)),
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
        ("add4", (0, 4, 5, 7)),
        ("add11", (0, 4, 7, 5)),
        ("7sus4", (0, 5, 7, 10)),
        ("sus2", (0, 2, 7)),
        ("add9(no3)", (0, 7, 2)),
        ("sus4", (0, 5, 7)),
        ("dim", (0, 3, 6)),
        ("aug", (0, 4, 8)),
        ("m", (0, 3, 7)),
        ("", (0, 4, 7)),
    ]


def _alterable_quality_bases() -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        sorted(
            (
                (suffix, intervals)
                for suffix, intervals in _chord_qualities()
                if suffix and "(no" not in suffix
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


_ALTERED_INTERVALS = {
    "b5": 6,
    "#5": 8,
    "b9": 1,
    "#9": 3,
    "#11": 6,
    "b13": 8,
}

_ALTERATION_REPLACEMENTS = {
    "b5": 7,
    "#5": 7,
    "b9": 2,
    "#9": 2,
    "#11": 5,
    "b13": 9,
}

_ALTERED_LETTER_STEPS = {
    "b5": 4,
    "#5": 4,
    "b9": 1,
    "#9": 1,
    "#11": 3,
    "b13": 5,
}
