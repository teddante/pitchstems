# PitchStems

PitchStems is a local-first desktop and CLI app for turning ordinary audio files into:

- separated stems
- per-stem MIDI files
- one combined multitrack MIDI file
- a ZIP archive for easy export

The intended pipeline is:

```text
audio file -> FFmpeg WAV normalization -> local stem separation -> Basic Pitch per stem -> MIDI export
```

No user audio needs to be uploaded to a cloud service.

## Features

- Drag-and-drop desktop GUI built with PySide6
- CLI for scripted local processing
- Fixed BS-RoFormer SW six-stem separation path
- Basic Pitch MIDI transcription per selected stem
- Rerun MIDI without rerunning stem separation
- Windows NVIDIA GPU path for PyTorch and ONNX Runtime
- Local model cache; no bundled model weights

The AI work is delegated to native local dependencies:

- [`bs-roformer-infer`](https://github.com/openmirlab/bs-roformer-infer) for BS-RoFormer source separation
- [`basic-pitch`](https://github.com/spotify/basic-pitch) for audio-to-MIDI transcription
- FFmpeg for broad audio format support

## Status

PitchStems is pre-1.0. The core local pipeline, CLI, and Qt GUI are working, but APIs and UI may still change.

## Recommended Python

Use Python 3.10 for the full local AI stack. Basic Pitch currently depends on a TensorFlow version range that does not resolve cleanly on Python 3.11+ on Windows.

## Install

CPU-oriented install:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[cpu,gui]"
```

Windows NVIDIA GPU install:

```powershell
.\scripts\setup-windows-gpu.ps1
```

FFmpeg must be available on `PATH`. On Windows, a full build from Gyan.dev works well.

The Windows GPU path uses:

- PyTorch CUDA for supported separation models
- ONNX Runtime GPU for ONNX-backed models
- Basic Pitch forced to its ONNX model so it can use ONNX Runtime's `CUDAExecutionProvider`

The setup script replaces default CPU wheels with PyTorch CUDA 12.8 wheels and installs ONNX Runtime GPU with CUDA/cuDNN runtime DLLs. This avoids the common Windows issue where `pip install torch` silently installs a CPU-only wheel.

If `pitchstems --doctor --gpu` does not show `OK` for both ONNX Runtime CUDA and PyTorch CUDA, the app may still run but it is not truly using the GPU path.

## Run

CLI:

```powershell
pitchstems --doctor
pitchstems --doctor --gpu
pitchstems --download-model bs_roformer_sw
pitchstems "C:\path\to\song.mp3" --output-dir "C:\path\to\exports"
pitchstems "C:\path\to\song.mp3" --model bs_roformer_sw --midi-policy pitched
pitchstems "C:\path\to\song.mp3" --bs-device cuda --onset-threshold 0.5 --frame-threshold 0.3
```

GUI:

```powershell
pitchstems-gui
```

## Model Downloads

Separation models are downloaded by the native `bs-roformer-infer` backend. Large models can be hundreds of megabytes, so the first run may spend time downloading before GPU processing starts.

PitchStems stores downloaded models here on Windows:

```text
%LOCALAPPDATA%\PitchStems\bs-roformer-models
```

To download a model ahead of time:

```powershell
pitchstems --download-model bs_roformer_sw
```

For `bs_roformer_sw`, PitchStems asks the native BS-RoFormer registry for `roformer-model-bs-roformer-sw-by-jarredou`. That registry downloads `BS-Rofo-SW-Fixed.ckpt` and `BS-Rofo-SW-Fixed.yaml`, currently from the model publisher's Hugging Face assets.

## GUI Workflow

The GUI is a native pipeline builder:

- use the fixed BS-RoFormer SW six-stem model for separation
- run the full separation + MIDI pipeline
- rerun only the Basic Pitch MIDI stage after stems already exist
- choose all stems or a single stem to save on the next full separation run
- tick exactly which saved stems Basic Pitch should analyse for MIDI
- see the native backend, registry id, actual model files, config file, expected stems, and GPU/runtime status

The app also exposes:

- BS-RoFormer's native `--device` choice: auto, CUDA GPU, or CPU
- Basic Pitch MIDI on/off
- per-stem MIDI analysis checkboxes, with drums off by default
- Basic Pitch's official MIDI parameters: onset threshold, frame threshold, minimum note length, note frequency limits, pitch-bend behavior, melodia post-processing, MIDI tempo, note CSV output, raw NPZ output, and MIDI sonification
- ZIP export on/off
- open output folder when finished
- open latest output folder button

The curated model catalog lives in `src/pitchstems/model_catalog.py`; the native BS-RoFormer runtime bridge lives in `src/pitchstems/separation.py`.

## Development

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest
python -m compileall src
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution notes.

## Native Settings

PitchStems intentionally exposes only settings that map to real backend arguments.

Audio import is prepared for the two model stages:

- before BS-RoFormer, FFmpeg converts the dropped file to stereo 44.1 kHz PCM WAV, matching the BS-RoFormer SW YAML audio settings (`sample_rate: 44100`, `num_channels: 2`)
- before Basic Pitch, the separated WAV stems are passed directly to Basic Pitch; Basic Pitch's own loader resamples internally to mono 22.05 kHz for the ICASSP 2022 model

BS-RoFormer separation uses `bs_roformer.inference.proc_folder` from `bs-roformer-infer`. The user-facing knobs are the model registry id and the Torch device. Model architecture, chunking, overlap, and instruments come from the downloaded model YAML because those are the publisher's intended settings for the checkpoint.

Basic Pitch MIDI uses `basic_pitch.inference.predict_and_save` with the ICASSP 2022 ONNX model. The exposed defaults match Basic Pitch:

- onset threshold: `0.5`
- frame threshold: `0.3`
- minimum note length: `127.7` ms
- minimum and maximum frequency: off by default
- multiple pitch bends: off by default
- melodia post-processing: on by default
- MIDI tempo: `120`
- note CSV output: on by default
- raw model output NPZ and MIDI sonification: off by default

## Notes

Basic Pitch is strongest on pitched material such as vocals, bass, guitar, piano, synth, and melodic "other" stems. Drum MIDI is skipped by default because Basic Pitch is not a drum transcription model.

## License

PitchStems is licensed under the MIT License. See [LICENSE](LICENSE).

Third-party dependencies and model assets have their own licenses and terms.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
