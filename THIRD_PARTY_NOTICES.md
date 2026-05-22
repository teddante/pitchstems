# Third-Party Notices

This project is MIT licensed, but it depends on third-party software and model
assets that have their own licenses and terms.

This file is informational and is not legal advice. Before distributing a
binary build, installer, hosted service, or bundled model package, re-audit the
exact dependency and model versions you ship.

## Runtime Dependencies

| Component | Purpose | License notes |
| --- | --- | --- |
| Basic Pitch | Audio-to-MIDI transcription | Apache-2.0 notices are present in the installed package. The upstream project is by Spotify AB. |
| bs-roformer-infer | Native BS-RoFormer inference and model registry | MIT license according to installed package metadata. |
| PySide6 / Qt for Python | Desktop GUI | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only according to installed package metadata. Dynamic linking/install-time dependency is intentional. |
| PyTorch | CUDA/CPU tensor runtime for separation | BSD-3-Clause according to installed package metadata. |
| ONNX Runtime GPU | ONNX inference runtime for Basic Pitch | MIT according to installed package metadata. |
| mido | MIDI file handling | MIT according to installed package metadata. |
| FFmpeg | Audio decoding/transcoding executable | External executable; users install it separately. FFmpeg builds may include components under multiple licenses depending on build options. |

## Model Assets

PitchStems downloads model weights and configs through the upstream
`bs-roformer-infer` registry. The current default model is:

- `roformer-model-bs-roformer-sw-by-jarredou`
- checkpoint: `BS-Rofo-SW-Fixed.ckpt`
- config: `BS-Rofo-SW-Fixed.yaml`

Model weights can have licensing or usage terms separate from the inference
code. PitchStems does not commit those weights to this repository.

## User Audio

Users are responsible for having the rights needed to process their own audio.
PitchStems runs locally and does not upload audio, but local processing can still
create derivative files such as separated stems and MIDI.
