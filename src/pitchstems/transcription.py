from __future__ import annotations

import importlib
import math
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from pitchstems.pipeline_models import MidiResult

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

    def __post_init__(self) -> None:
        for label, value in (
            ("onset threshold", self.onset_threshold),
            ("frame threshold", self.frame_threshold),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"MIDI {label} must be between 0 and 1.")
        if not math.isfinite(self.minimum_note_length) or self.minimum_note_length < 0:
            raise ValueError("MIDI minimum note length must be zero or greater.")
        if self.minimum_frequency is not None and (
            not math.isfinite(self.minimum_frequency) or self.minimum_frequency <= 0
        ):
            raise ValueError("MIDI minimum frequency must be a positive finite value.")
        if self.maximum_frequency is not None and (
            not math.isfinite(self.maximum_frequency) or self.maximum_frequency <= 0
        ):
            raise ValueError("MIDI maximum frequency must be a positive finite value.")
        if (
            self.minimum_frequency is not None
            and self.maximum_frequency is not None
            and self.minimum_frequency > self.maximum_frequency
        ):
            raise ValueError("MIDI minimum frequency must not exceed maximum frequency.")
        if not math.isfinite(self.midi_tempo) or self.midi_tempo <= 0:
            raise ValueError("MIDI tempo must be a positive finite value.")
        if self.sonification_samplerate <= 0:
            raise ValueError("MIDI sonification sample rate must be positive.")


DEFAULT_MIDI_OPTIONS = MidiOptions()


@dataclass(frozen=True)
class MidiOptionSpec:
    field: str
    label: str
    cli_flag: str
    help: str
    default_suffix: str = ""
    default_precision: int | None = None
    default_when_none: str | None = None
    checkbox_label: str | None = None
    tooltip_detail: str = ""

    def default_value(self) -> object:
        return getattr(DEFAULT_MIDI_OPTIONS, self.field)

    def default_label(self) -> str:
        value = self.default_value()
        if value is None:
            return self.default_when_none or "off"
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, float):
            if self.default_precision is not None:
                text = f"{value:.{self.default_precision}f}"
            else:
                text = f"{value:g}"
        else:
            text = str(value)
        return f"{text}{self.default_suffix}"

    def default_hint(self) -> str:
        return f"default {self.default_label()}"

    def checkbox_text(self) -> str:
        label = self.checkbox_label or self.label
        return f"{label} (default {self.default_label()})"

    def gui_tooltip(self) -> str:
        detail = f" {self.tooltip_detail}" if self.tooltip_detail else ""
        return f"Basic Pitch default: {self.default_label()}.{detail}"


MIDI_OPTION_SPECS: tuple[MidiOptionSpec, ...] = (
    MidiOptionSpec(
        "onset_threshold",
        "Note starts",
        "--onset-threshold",
        "Basic Pitch onset confidence threshold.",
        default_precision=2,
        tooltip_detail="Higher means fewer detected note attacks; lower means more sensitive note starts.",
    ),
    MidiOptionSpec(
        "frame_threshold",
        "Sustained notes",
        "--frame-threshold",
        "Basic Pitch frame confidence threshold.",
        default_precision=2,
        tooltip_detail="Higher means stricter sustained-note detection; lower keeps more quiet/ambiguous frames.",
    ),
    MidiOptionSpec(
        "minimum_note_length",
        "Minimum note",
        "--minimum-note-length",
        "Basic Pitch minimum note length in milliseconds.",
        default_suffix=" ms",
        tooltip_detail="Notes shorter than this are filtered out.",
    ),
    MidiOptionSpec(
        "minimum_frequency",
        "Lowest note",
        "--minimum-frequency",
        "Basic Pitch minimum output frequency in Hz.",
        default_when_none="off",
        tooltip_detail="No lower frequency limit.",
    ),
    MidiOptionSpec(
        "maximum_frequency",
        "Highest note",
        "--maximum-frequency",
        "Basic Pitch maximum output frequency in Hz.",
        default_when_none="off",
        tooltip_detail="No upper frequency limit.",
    ),
    MidiOptionSpec(
        "midi_tempo",
        "MIDI tempo",
        "--midi-tempo",
        "Tempo written into generated MIDI files.",
        default_suffix=" BPM",
        tooltip_detail="This is MIDI metadata, not audio time-stretching.",
    ),
    MidiOptionSpec(
        "melodia_trick",
        "Melodia",
        "--no-melodia-trick",
        "Disable Basic Pitch's default melodia post-processing step.",
        checkbox_label="Melodia post-processing",
        tooltip_detail="Helps turn frame/onset predictions into cleaner note events.",
    ),
    MidiOptionSpec(
        "multiple_pitch_bends",
        "Pitch bends",
        "--multiple-pitch-bends",
        "Allow overlapping MIDI notes to carry separate pitch bends.",
        checkbox_label="Separate pitch bends for overlapping notes",
        tooltip_detail="Useful for expressive material, but can make MIDI more complex.",
    ),
    MidiOptionSpec(
        "save_notes",
        "Save notes",
        "--no-save-notes",
        "Do not save Basic Pitch note-event CSV files.",
        checkbox_label="Save note-event CSV",
    ),
    MidiOptionSpec(
        "save_model_outputs",
        "Save model outputs",
        "--save-model-outputs",
        "Save Basic Pitch raw model outputs as NPZ files.",
        checkbox_label="Save raw model output NPZ",
        tooltip_detail="Technical/debug output: contours, onsets, and note activations.",
    ),
    MidiOptionSpec(
        "sonify_midi",
        "Render MIDI check audio",
        "--sonify-midi",
        "Render Basic Pitch MIDI back to audio for checking.",
    ),
    MidiOptionSpec(
        "sonification_samplerate",
        "Check audio rate",
        "--sonification-samplerate",
        "Sample rate for --sonify-midi output.",
    ),
)
MIDI_OPTION_SPEC_BY_FIELD = {spec.field: spec for spec in MIDI_OPTION_SPECS}


def midi_option_spec(field: str) -> MidiOptionSpec:
    return MIDI_OPTION_SPEC_BY_FIELD[field]


def optional_frequency_limit(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return value


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
        model, runtime = load_basic_pitch_runtime()
        predict_and_save = importlib.import_module("basic_pitch.inference").predict_and_save
    except ImportError as exc:
        raise TranscriptionDependencyError(
            "basic-pitch is not installed. Install with `pip install -e .[cpu,gui]` "
            "or `pip install -e .[win-gpu,gui]`."
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    if log:
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
        model_or_model_path=model,
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


@lru_cache(maxsize=1)
def _load_basic_pitch_model(model_path: str) -> object:
    model_class = importlib.import_module("basic_pitch.inference").Model

    return model_class(model_path)


def load_basic_pitch_runtime() -> tuple[object, str]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="resampy.filters",
        )
        basic_pitch = importlib.import_module("basic_pitch")

    model_path = basic_pitch.build_icassp_2022_model_path(basic_pitch.FilenameSuffix.onnx)
    model = _load_basic_pitch_model(str(model_path))
    return model, _basic_pitch_provider_label(model)


def _basic_pitch_provider_label(model: object) -> str:
    session = getattr(model, "model", None)
    get_providers = getattr(session, "get_providers", None)
    if not callable(get_providers):
        return "ONNX provider unknown"
    try:
        providers = get_providers()
    except Exception:
        return "ONNX provider unknown"
    if not providers:
        return "ONNX provider unknown"
    active = str(providers[0])
    if active == "CUDAExecutionProvider":
        return "ONNX CUDA"
    if active == "CPUExecutionProvider":
        return "ONNX CPU"
    return f"ONNX {active.removesuffix('ExecutionProvider')}"


def _format_frequency_range(options: MidiOptions) -> str:
    low = f"{options.minimum_frequency:g} Hz" if options.minimum_frequency else "no low cut"
    high = f"{options.maximum_frequency:g} Hz" if options.maximum_frequency else "no high cut"
    return f"{low} to {high}"
