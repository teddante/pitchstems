from __future__ import annotations

from pitchstems.editor_project import ChordRegion


def playback_loop_range(
    selection: tuple[float, float] | None,
    selected_chord: ChordRegion | None,
) -> tuple[float, float] | None:
    if selection is not None:
        return selection
    if selected_chord is None:
        return None
    return selected_chord.start, selected_chord.end
