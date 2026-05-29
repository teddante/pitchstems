from __future__ import annotations

from pitchstems.editor_project import EditorProject, NoteEvent, midi_velocity_energy
from pitchstems.notation import pitch_class_for_name, spelling_preference_from_label


HarmonyContextKey = tuple[str, float] | tuple[str, float, float]


def resolve_notation_preference(
    selected_preference: str,
    theory_label: str | None = None,
    chord_label: str | None = None,
) -> str:
    if selected_preference != "auto":
        return selected_preference
    theory_preference = spelling_preference_from_label(theory_label)
    if theory_preference != "auto":
        return theory_preference
    chord_preference = spelling_preference_from_label(chord_label)
    if chord_preference != "auto":
        return chord_preference
    return "auto"


def harmony_context_key(
    seconds: float,
    selection: tuple[float, float] | None,
) -> HarmonyContextKey:
    if selection is not None:
        start, end = selection
        return ("selection", round(start, 3), round(end, 3))
    return ("point", round(seconds, 2))


def selected_chord_analysis_notes(
    project: EditorProject | None,
    selected_track_names: set[str] | None,
) -> list[NoteEvent]:
    if project is None:
        return []
    if selected_track_names is None:
        return project.notes
    selected = {name.lower() for name in selected_track_names}
    return [note for note in project.notes if note.stem.lower() in selected]


def chord_analysis_track_names(
    project: EditorProject | None,
    selected_track_names: set[str] | None,
) -> list[str]:
    if project is None:
        return []
    if selected_track_names is None:
        return [
            track.name
            for track in project.tracks
            if any(note.stem.lower() == track.name.lower() for note in project.notes)
        ]
    selected = {name.lower() for name in selected_track_names}
    return [track.name for track in project.tracks if track.name.lower() in selected]


def chord_sample_text(track_names: list[str], note_count: int) -> str:
    if not track_names:
        return "Sample: no tracks selected. Tick Chord to include a track."
    shown = ", ".join(track_names[:5])
    if len(track_names) > 5:
        shown += f", +{len(track_names) - 5} more"
    return f"Sample: {shown} ({note_count} MIDI notes). View, Audio, and MIDI ticks do not affect detection."


def chord_note_constraints(overrides: dict[int, str]) -> tuple[set[int], set[int]]:
    required = {pitch_class for pitch_class, state in overrides.items() if state == "force"}
    excluded = {pitch_class for pitch_class, state in overrides.items() if state == "exclude"}
    return required, excluded


def filtered_chord_analysis_notes(
    notes: list[NoteEvent],
    excluded_pitch_classes: set[int],
) -> list[NoteEvent]:
    return [note for note in notes if note.pitch % 12 not in excluded_pitch_classes]


def chord_base_pitch_weights(
    notes: list[NoteEvent],
    context: HarmonyContextKey,
) -> dict[int, float]:
    if not notes:
        return {}
    weights: dict[int, float] = {}
    if context[0] == "selection":
        _kind, start, end = context
        for note in notes:
            overlap = max(0.0, min(note.end, end) - max(note.start, start))
            if overlap <= 0:
                continue
            weights[note.pitch % 12] = (
                weights.get(note.pitch % 12, 0.0)
                + overlap * midi_velocity_energy(note.velocity)
            )
    else:
        _kind, seconds = context
        for note in notes:
            if note.start <= seconds < note.end:
                weights[note.pitch % 12] = max(
                    weights.get(note.pitch % 12, 0.0),
                    midi_velocity_energy(note.velocity),
                )
    if not weights:
        return {}
    maximum = max(weights.values())
    return {pitch_class: weight / maximum for pitch_class, weight in weights.items()}


def pitch_class_for_weighted_note(note_name: str) -> int | None:
    return pitch_class_for_name(note_name)
