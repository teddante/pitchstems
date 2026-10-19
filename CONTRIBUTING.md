# Contributing

Thanks for helping improve PitchStems.

## Development Setup

Use Python 3.10 or 3.11. Apple-silicon Macs should continue using Python 3.10
for the current Basic Pitch 0.4.0 runtime.

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

Validation tiers:

- Fast source check with the local runtime stack: `.\scripts\check.ps1`
- Source-only check without the ML/GUI runtime stack: `.\scripts\check.ps1 -SkipDoctor`
- CI (`.github/workflows/check.yml`) runs `.\scripts\check.ps1 -SkipDoctor -GuiSmoke` on Windows with the CPU stack for every push to `main` and every pull request.
- GUI/package check: `.\scripts\check.ps1 -GuiSmoke -Build`
- GPU/runtime check after GPU setup, acceleration, model runtime, launcher, or
  packaging changes: `.\scripts\check.ps1 -Gpu`
- Dependency security audit when dependency files change: `python -m pip_audit`

The project check runs Ruff, Vulture, mypy, the tests with a focused core
coverage gate, `compileall`, `python -m pip check`, and Git whitespace checks
for the working tree, staged changes, and branch diff when `main` is available.
The coverage percentage is a focused core-module gate, not a whole-package
claim. When adding a module to mypy or coverage gates, keep the change small:
add focused tests first, add the module to the gate, then run
`.\scripts\check.ps1`. Do not lower coverage thresholds to make unrelated work
pass.

For reproducible Windows installs, use the constraints files in `constraints/`
with the matching extra. Regenerate them from a clean Windows environment after
changing dependencies, and only after `.\scripts\check.ps1 -GuiSmoke -Build`
and `python -m pip check` pass:

```powershell
py -3.10 scripts
efresh_constraints.py dev
py -3.10 scripts
efresh_constraints.py cpu
```

### Real-audio smoke

When changing separation, transcription, project packaging, editor review, or
export behavior, run the real-audio smoke with a short local audio file (never
a committed song or generated stem output):

```powershell
.\scripts\real_audio_smoke.ps1 -AudioPath "C:\path\to\short-audio.mp3"
```

It runs the real CLI pipeline, reopens the generated `.pitchstems` project in
the offscreen GUI, checks timeline review/playback, and copies selected export
files. A passing run prints the project folder and a `selected-export` folder
containing selected stems and MIDI; source audio stays unchecked by default.

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
