# PitchStems

PitchStems is a local-first desktop and CLI app for turning ordinary audio files into:

- reusable `.pitchstems` project folders
- separated stems
- per-stem MIDI files
- one combined multitrack MIDI file
- a ZIP archive for easy export

The intended pipeline is:

```text
audio file -> .pitchstems project -> FFmpeg WAV normalization -> local stem separation -> Basic Pitch per stem -> MIDI export
```

No user audio needs to be uploaded to a cloud service.

## Features

- Drag-and-drop desktop GUI built with PySide6
- CLI for scripted local processing
- Fixed BS-RoFormer SW six-stem separation path
- Basic Pitch MIDI transcription per selected stem
- First-pass editor timeline for inspecting stem MIDI notes and inferred chord regions
- Project manifest for reopening completed stem/MIDI/editor timelines without rerunning models
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
python -m pip install -c constraints\windows-cpu.txt -e ".[cpu,gui]"
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

The setup script replaces default CPU wheels with PyTorch CUDA 12.8 wheels and installs ONNX Runtime GPU with CUDA/cuDNN runtime DLLs. This avoids the common Windows issue where `pip install torch` silently installs a CPU-only wheel. The supported Windows GPU package pins live in `constraints/windows-gpu.txt`; keep that file and `scripts/setup-windows-gpu.ps1` aligned when changing the runtime stack.

The GPU setup keeps both `onnxruntime` package metadata and `onnxruntime-gpu`
installed. Basic Pitch declares `onnxruntime`, while PitchStems imports ONNX
Runtime from the GPU wheel so CUDA providers remain available. `pip check` is
part of the project check and should pass after setup.

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
- ZIP export package on/off
- open output folder when finished
- File menu actions for opening projects, choosing the output folder, and opening the latest output folder

After a successful GUI run, the Editor tab builds a first-pass timeline from the generated
MIDI files. It shows stem lanes, note events, inferred chord regions, a scrubber/playhead,
and per-track checkboxes for hiding or showing MIDI notes while reviewing the transcription.
The editor transport can play separated stem audio and lightweight generated MIDI preview
audio in sync, with per-track mute and volume controls saved in the project.

Each full GUI or CLI run creates a project folder ending in `.pitchstems`. The folder keeps
one canonical copy of the project audio assets: the copied source audio, normalized work
audio, generated stems, MIDI, and a `pitchstems.project.json` manifest. ZIP packages are
optional, and stem WAVs are not duplicated into `export`.
Use **Open Project** in the GUI to reopen that manifest without rerunning the expensive
separation step.

GUI cancellation runs the expensive full-pipeline and MIDI-rerun jobs in a child
process so Cancel can stop native BS-RoFormer or Basic Pitch work without waiting
for the model call to return. CLI cancellation remains cooperative inside one
process. For the technical boundary and cleanup rules, see
`docs/architecture/native-job-cancellation.md`.

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
python -m pip check
git diff --check main...HEAD
```

For reproducible Windows installs, use the constraints files in `constraints/`
with the matching extra. Refresh constraints only after
`.\scripts\check.ps1 -GuiSmoke -Build` and `python -m pip check` pass.

Validation tiers:

- Fast source check: `.\scripts\check.ps1`
- GUI/package check: `.\scripts\check.ps1 -GuiSmoke -Build`
- GPU/runtime check after setup or ML dependency changes: `.\scripts\check.ps1 -Gpu`
- Dependency security audit: `python -m pip_audit`
- Manual real-audio smoke when changing separation/transcription or editor review/export behavior:

See `docs/architecture/quality-gate-roadmap.md` for the current typed/coverage surface and known gaps.

```powershell
.\scripts\real_audio_smoke.ps1 -AudioPath "C:\path\to\short-audio.mp3"
```

Use a short local audio fixture, not a committed song or generated stem output. The smoke script runs the real CLI pipeline, reopens the generated `.pitchstems` project in the offscreen GUI, checks timeline review/playback, and copies selected export files to prove the import audio -> separate -> MIDI -> reopen project -> play/review -> export selected files path.

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
