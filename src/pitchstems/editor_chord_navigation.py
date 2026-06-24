from __future__ import annotations

from pitchstems.editor_project import ChordRegion


def review_navigation_chord(
    chords: list[ChordRegion],
    selected_chord: ChordRegion | None,
    position_seconds: float,
    direction: int,
) -> ChordRegion | None:
    if not chords or direction == 0:
        return None
    if selected_chord in chords:
        index = chords.index(selected_chord)
        next_index = max(0, min(len(chords) - 1, index + (1 if direction > 0 else -1)))
        return chords[next_index]
    if direction > 0:
        for chord in chords:
            if chord.end > position_seconds:
                return chord
        return chords[-1]
    for chord in reversed(chords):
        if chord.start <= position_seconds:
            return chord
    return chords[0]
