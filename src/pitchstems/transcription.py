from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pitchstems.acceleration import onnxruntime_status

PERCUSSIVE_STEMS = {"drums", "drum", "kick", "snare", "toms", "hh", "hats", "ride", "crash"}


@dataclass(frozen=True)
class MidiOptions:
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    minimum_note_length: float = 127.7
    minimum_frequency: float | None = None
    maximum_frequency: float | None = None
    multiple_pitch_bends: bool = False
    melodia_trick: bool = True
    midi_tempo: float = 120.0
    save_notes: bool = True
    save_model_outputs: bool = False
    sonify_midi: bool = False
    sonification_samplerate: int = 44100


@dataclass(frozen=True)
class MidiResult:
    stem: str
    path: Path


class TranscriptionDependencyError(RuntimeError):
    """Raised when Basic Pitch is not installed."""


def transcribe_stem_to_midi(
    stem_name: str,
    audio_path: Path,
    output_dir: Path,
    skip_percussion: bool = True,
    options: MidiOptions | None = None,
    log: Callable[[str], None] | None = None,
) -> MidiResult | None:
    """Run Basic Pitch on one separated stem and return the generated MIDI path."""
    options = options or MidiOptions()
    if skip_percussion and stem_name.lower() in PERCUSSIVE_STEMS:
        if log:
            log(f"Skipping percussive MIDI for {audio_path.name}.")
        return None

    try:
        from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
        from basic_pitch.inference import predict_and_save
    except ImportError as exc:
        raise TranscriptionDependencyError(
            "basic-pitch is not installed. Install with `pip install -e .[cpu,gui]` "
            "or `pip install -e .[win-gpu,gui]`."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = build_icassp_2022_model_path(FilenameSuffix.onnx)
    ort_status = onnxruntime_status()
    if log:
        runtime = "ONNX CUDA" if ort_status.has_cuda else "ONNX CPU"
        log(f"Transcribing {stem_name} with Basic Pitch ({runtime})...")
        log(
            "Basic Pitch settings: "
            f"onset={options.onset_threshold:g}, frame={options.frame_threshold:g}, "
            f"min_note_ms={options.minimum_note_length:g}, "
            f"frequency={_format_frequency_range(options)}, "
            f"melodia={'on' if options.melodia_trick else 'off'}, "
            f"pitch_bends={'multi' if options.multiple_pitch_bends else 'single'}, "
            f"tempo={options.midi_tempo:g}"
        )

    predict_and_save(
        [str(audio_path)],
        str(output_dir),
        save_midi=True,
        sonify_midi=options.sonify_midi,
        save_model_outputs=options.save_model_outputs,
        save_notes=options.save_notes,
        model_or_model_path=model_path,
        onset_threshold=options.onset_threshold,
        frame_threshold=options.frame_threshold,
        minimum_note_length=options.minimum_note_length,
        minimum_frequency=options.minimum_frequency,
        maximum_frequency=options.maximum_frequency,
        multiple_pitch_bends=options.multiple_pitch_bends,
        melodia_trick=options.melodia_trick,
        sonification_samplerate=options.sonification_samplerate,
        midi_tempo=options.midi_tempo,
    )

    midi_candidates = sorted(output_dir.glob(f"{audio_path.stem}*.mid"))
    if not midi_candidates:
        midi_candidates = sorted(output_dir.glob("*.mid"))
    if not midi_candidates:
        raise RuntimeError(f"Basic Pitch did not create a MIDI file for {audio_path.name}.")

    return MidiResult(stem=stem_name, path=midi_candidates[-1])


def _format_frequency_range(options: MidiOptions) -> str:
    low = f"{options.minimum_frequency:g} Hz" if options.minimum_frequency else "no low cut"
    high = f"{options.maximum_frequency:g} Hz" if options.maximum_frequency else "no high cut"
    return f"{low} to {high}"
