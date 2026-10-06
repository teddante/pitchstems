from __future__ import annotations

import wave
from array import array
from pathlib import Path

from pitchstems.atomic_files import atomic_replace
from pitchstems.editor_models import NoteEvent
from pitchstems.filename_safety import safe_file_stem
from pitchstems.midi_synth import MidiSynthEngine


def render_note_preview(
    name: str,
    notes: list[NoteEvent],
    output_dir: Path,
    duration: float = 1.6,
    sample_rate: int = 22_050,
) -> Path | None:
    """Render a short one-shot preview WAV with the same voice as the live MIDI synth."""
    if not notes:
        return None

    engine = MidiSynthEngine(notes, duration, sample_rate)
    frame_count = max(1, int((duration + 0.15) * sample_rate))
    samples = engine.render_samples(0.0, frame_count, {stem: 1.0 for stem in engine.stems})
    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak <= 0:
        return None
    scale = min(0.92 / peak, 1.0)
    pcm = array("h", (int(max(-1.0, min(1.0, sample * scale)) * 32767) for sample in samples))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_file_stem(name, fallback='preview')}.wav"
    with atomic_replace(output_path) as temporary, wave.open(str(temporary), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return output_path
