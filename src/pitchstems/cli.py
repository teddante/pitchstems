from __future__ import annotations

import argparse
from pathlib import Path

from pitchstems.doctor import format_checks, run_checks
from pitchstems.model_catalog import all_model_keys, model_choice
from pitchstems.pipeline import process_audio_file
from pitchstems.separation import download_model, model_key_for_profile, profile_keys
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import DEFAULT_MIDI_OPTIONS, MidiOptions


def main() -> int:
    parser = argparse.ArgumentParser(description="Separate audio into stems and transcribe MIDI locally.")
    parser.add_argument("audio_file", nargs="?", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "pitchstems-output")
    parser.add_argument("--quality", choices=profile_keys(), default="song-6-stem")
    parser.add_argument("--model", choices=all_model_keys(), help="Choose a compatible curated model directly.")
    parser.add_argument(
        "--download-model",
        choices=all_model_keys(),
        help="Download a curated model to the local PitchStems cache without processing audio.",
    )
    parser.add_argument("--stem", help="Only output this stem if the selected model supports it.")
    parser.add_argument(
        "--bs-device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Torch device for native BS-RoFormer separation. Auto uses CUDA when PyTorch can see it.",
    )
    parser.add_argument(
        "--bs-device-id",
        type=int,
        action="append",
        help="Optional GPU id for BS-RoFormer DataParallel. Repeat for more than one GPU.",
    )
    parser.add_argument("--no-midi", action="store_true", help="Only separate stems; do not run Basic Pitch.")
    parser.add_argument(
        "--midi-policy",
        choices=["pitched", "all", "none"],
        default="pitched",
        help="Choose which stems get Basic Pitch MIDI.",
    )
    parser.add_argument(
        "--onset-threshold",
        type=float,
        default=DEFAULT_MIDI_OPTIONS.onset_threshold,
        help="Basic Pitch onset confidence threshold.",
    )
    parser.add_argument(
        "--frame-threshold",
        type=float,
        default=DEFAULT_MIDI_OPTIONS.frame_threshold,
        help="Basic Pitch frame confidence threshold.",
    )
    parser.add_argument(
        "--minimum-note-length",
        type=float,
        default=DEFAULT_MIDI_OPTIONS.minimum_note_length,
        help="Basic Pitch minimum note length in milliseconds.",
    )
    parser.add_argument("--minimum-frequency", type=float, help="Basic Pitch minimum output frequency in Hz.")
    parser.add_argument("--maximum-frequency", type=float, help="Basic Pitch maximum output frequency in Hz.")
    parser.add_argument("--multiple-pitch-bends", action="store_true", help="Allow overlapping MIDI notes to carry separate pitch bends.")
    parser.add_argument("--no-melodia-trick", action="store_true", help="Disable Basic Pitch's default melodia post-processing step.")
    parser.add_argument(
        "--midi-tempo",
        type=float,
        default=DEFAULT_MIDI_OPTIONS.midi_tempo,
        help="Tempo written into generated MIDI files.",
    )
    parser.add_argument("--no-save-notes", action="store_true", help="Do not save Basic Pitch note-event CSV files.")
    parser.add_argument("--save-model-outputs", action="store_true", help="Save Basic Pitch raw model outputs as NPZ files.")
    parser.add_argument("--sonify-midi", action="store_true", help="Render Basic Pitch MIDI back to audio for checking.")
    parser.add_argument(
        "--sonification-samplerate",
        type=int,
        default=DEFAULT_MIDI_OPTIONS.sonification_samplerate,
        help="Sample rate for --sonify-midi output.",
    )
    parser.add_argument("--no-zip", action="store_true", help="Leave outputs in a folder without ZIP export.")
    parser.add_argument("--doctor", action="store_true", help="Check local runtime dependencies.")
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="With --doctor, also require Windows GPU acceleration checks.",
    )
    args = parser.parse_args()

    if args.doctor:
        checks = run_checks(require_gpu=args.gpu)
        print(format_checks(checks))
        return 0 if all(check.ok for check in checks) else 1

    if args.download_model:
        model_dir = download_model(args.download_model, log=print)
        print(f"Cached in: {model_dir}")
        return 0

    if not args.audio_file:
        parser.error("audio_file is required unless --doctor or --download-model is used")

    separation_options = _separation_options(args)
    model_key = separation_options.model_key if separation_options else model_key_for_profile(args.quality)
    choice = model_choice(model_key)
    selected_stem = args.stem
    if selected_stem and selected_stem.lower() not in {stem.lower() for stem in choice.stems}:
        parser.error(f"--stem {selected_stem!r} is not supported by --model {model_key}. Valid stems: {', '.join(choice.stems)}")
    midi_options = MidiOptions(
        onset_threshold=args.onset_threshold,
        frame_threshold=args.frame_threshold,
        minimum_note_length=args.minimum_note_length,
        minimum_frequency=args.minimum_frequency,
        maximum_frequency=args.maximum_frequency,
        multiple_pitch_bends=args.multiple_pitch_bends,
        melodia_trick=not args.no_melodia_trick,
        midi_tempo=args.midi_tempo,
        save_notes=not args.no_save_notes,
        save_model_outputs=args.save_model_outputs,
        sonify_midi=args.sonify_midi,
        sonification_samplerate=args.sonification_samplerate,
    )

    result = process_audio_file(
        args.audio_file,
        args.output_dir,
        quality=args.quality,
        separation_options=separation_options,
        generate_midi=not args.no_midi,
        midi_policy="none" if args.no_midi else args.midi_policy,
        midi_options=midi_options,
        create_zip=not args.no_zip,
        log=print,
    )
    print(result.zip_path or result.project_dir)
    return 0


def _bs_device(device: str) -> str | None:
    if device == "cuda":
        return "cuda:0"
    if device == "cpu":
        return "cpu"
    return None


def _separation_options(args: argparse.Namespace) -> SeparationOptions | None:
    explicit_device = args.bs_device != "auto" or bool(args.bs_device_id)
    if not (args.model or args.stem or explicit_device):
        return None
    return SeparationOptions(
        model_key=args.model or model_key_for_profile(args.quality),
        selected_stem=args.stem,
        device=_bs_device(args.bs_device),
        device_ids=tuple(args.bs_device_id) if args.bs_device_id else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
