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
python -m pip install -c constraints\windows-cpu.txt -e ".[gui,cpu]"
```

On Windows with an NVIDIA GPU, use:

```powershell
.\scripts\setup-windows-gpu.ps1
```

The supported Windows GPU pins live in `constraints/windows-gpu.txt`; keep that
file aligned with `scripts/setup-windows-gpu.ps1` when changing ML runtimes.

## Checks

Run these before opening a pull request:

```powershell
.\scripts\check.ps1
```

The project check also runs `python -m pip check` so broken installed
dependency metadata is caught before review. It also runs Git whitespace checks
for the working tree, staged changes, and branch diff when `main` is available.
When adding a module to mypy or coverage gates, keep the change small: add
focused tests first, add the module to the gate, then run `.\scripts\check.ps1`.
Do not lower coverage thresholds to make unrelated work pass.

For a focused branch whitespace check, run:

```powershell
git diff --check main...HEAD
```

Use the GPU check when changing GPU setup, acceleration code, model runtime,
launcher behavior, or packaging:

```powershell
.\scripts\check.ps1 -Gpu
```

When changing separation, transcription, project packaging, or editor timeline
loading, run a short real-audio smoke through the CLI, reopen the generated
`.pitchstems` project in the GUI, and confirm stems, MIDI, combined MIDI,
manifest, timeline playback, and optional ZIP export are present.
When dependency files change, run `python -m pip_audit` in the constrained dev
environment or inspect the dependency-audit workflow result before merging.

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
