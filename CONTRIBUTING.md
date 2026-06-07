# Contributing

Thanks for helping improve PitchStems.

## Development Setup

Use Python 3.10.

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For full local audio processing, install the optional GUI/ML extras:

```powershell
python -m pip install -e ".[gui,cpu]"
```

On Windows with an NVIDIA GPU, use:

```powershell
.\scripts\setup-windows-gpu.ps1
```

## Checks

Run these before opening a pull request:

```powershell
.\scripts\check.ps1
```

The project check also runs `python -m pip check` so broken installed
dependency metadata is caught before review.

Use the GPU check when changing GPU setup, acceleration code, model runtime,
launcher behavior, or packaging:

```powershell
.\scripts\check.ps1 -Gpu
```

See [AGENTS.md](AGENTS.md) for the solo-development branch, commit, pull
request, release, and approval workflow used by AI-assisted development.

## Project Boundaries

- Keep the app local-first. Do not upload user audio.
- Do not commit model weights, generated stems, generated MIDI, ZIP exports, or user audio.
- Prefer real upstream settings over invented presets.
- Keep the GUI focused on the fixed BS-RoFormer SW six-stem workflow unless a new model path is clearly justified.

## Legal Hygiene

When adding a dependency, update `THIRD_PARTY_NOTICES.md` with its purpose and
license notes. When bundling anything beyond source code, re-check the license
of the exact artifact being distributed.
