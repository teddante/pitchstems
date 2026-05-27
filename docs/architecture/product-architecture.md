# PitchStems Product Architecture

PitchStems is evolving from a working local-first Python/PySide prototype into a more structured desktop product. The goal is to keep the current app usable while moving toward a cleaner frontend/backend architecture.

## Direction

Use a modern desktop shell and frontend for the product UI, while keeping Python as the local ML/audio backend.

Preferred target stack:

- Desktop shell: Tauri 2
- Frontend: Svelte/SvelteKit with TypeScript
- Backend: Python sidecar process for audio, ML, MIDI, and music-theory work
- Project store: SQLite plus project asset folders
- Timeline renderer: Canvas 2D first, with WebGL only if proven necessary
- IPC: typed command/request messages plus streamed job events

## Core Principles

- Keep the current PySide app working until the new app reaches useful parity.
- Move domain logic out of UI code before replacing UI code.
- Treat long-running work as jobs with stable `job_id` and `project_id` values.
- Store large audio/MIDI/rendered assets as files, not database blobs.
- Store structured project state, notes, tracks, chord regions, and settings in SQLite.
- Make stale background work harmless by requiring project/job identity checks.
- Prefer documented schemas over implicit UI state.
- Avoid rewriting working ML/audio code unless a specific bottleneck proves it is needed.

## Target Runtime Shape

```text
Tauri desktop process
  owns app windows, menus, filesystem permissions, updates, and sidecar lifecycle

Svelte frontend
  owns timeline UI, panels, transport controls, project browser, and inspectors

Python backend sidecar
  owns BS-RoFormer, Basic Pitch, MIDI parsing/rendering, chord analysis, project jobs

Project storage
  owns durable local state through SQLite and asset folders
```

## Suggested Repository Shape

```text
apps/
  desktop/              Tauri app shell
  web/                  Svelte/SvelteKit frontend
backend/
  pitchstems_core/      Python audio, MIDI, project, and chord modules
  pitchstems_api/       Python sidecar API and job runner
crates/
  pitchstems_host/      Rust/Tauri host code
shared/
  schemas/              JSON schemas and generated TypeScript types
docs/
  architecture/         Architecture notes and decisions
```

The existing `src/pitchstems` package can be migrated toward `backend/pitchstems_core` gradually. The current layout does not need to move immediately.

## Backend Modules

The Python backend should be split around responsibilities:

```text
audio/
  ffmpeg conversion, audio metadata, preview assets
separation/
  BS-RoFormer model selection and inference
transcription/
  Basic Pitch inference and MIDI outputs
midi/
  MIDI parsing, rendering, note-event utilities
chords/
  evidence.py       MIDI evidence and pitch-class weights
  naming.py         valid chord names and aliases
  detection.py      scoring and candidate ranking
  explanation.py    human-readable calculation reports
project/
  schema.py         project schema models
  storage.py        SQLite and asset folder access
  migrations.py     schema migrations
jobs/
  runner.py         job execution and cancellation
  events.py         progress, log, result, and failure events
```

## IPC Shape

Use explicit messages. Every long-running operation should include project and job identity.

```json
{
  "type": "job.progress",
  "projectId": "project_123",
  "jobId": "job_456",
  "stage": "transcription",
  "message": "Running Basic Pitch on piano",
  "percent": 42
}
```

The frontend should ignore events for any project/job that is no longer current.

## Project Folder Shape

```text
My Song.pitchstems/
  project.sqlite
  project.pitchstems.json
  audio/
  stems/
  midi/
  previews/
  waveforms/
  cache/
  exports/
```

SQLite stores structured data. Folders store large or rebuildable artifacts.

## Migration Phases

1. Extract non-UI logic from the current PySide app into testable Python modules.
2. Define project, job, timeline, track, note, and chord schemas.
3. Add a Python sidecar API around the extracted core.
4. Scaffold the Tauri/Svelte app and prove project-open plus timeline read-only display.
5. Add transport, chord inspector, mixer, and job progress.
6. Move separation/transcription workflows into the new frontend.
7. Retire the PySide UI when the new app can cover normal use.

## Non-Goals For The First Pass

- Do not rewrite BS-RoFormer or Basic Pitch integration in Rust.
- Do not replace Python for ML/audio orchestration.
- Do not migrate all project storage at once.
- Do not break the current PySide GUI while exploring the new product architecture.
