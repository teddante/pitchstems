# ADR 0001: Product Architecture Direction

## Status

Accepted

## Context

PitchStems currently has a working Python/PySide6 desktop app with a local-first audio pipeline, GPU-capable model execution, MIDI transcription, timeline editing, chord inspection, and project storage.

The app is becoming more product-like, and the UI/editor surface is now large enough that continuing to grow one PySide file will make the project harder to maintain. At the same time, the ML/audio ecosystem still strongly favors Python.

## Decision

PitchStems will evolve toward a Tauri + Svelte/SvelteKit frontend with a Python local backend sidecar.

The current PySide app remains the working product while the architecture is migrated gradually.

## Consequences

Positive:

- The UI can use a modern frontend architecture and dedicated rendering surfaces.
- Python remains responsible for ML, audio, MIDI, and chord analysis.
- The backend can become testable without GUI dependencies.
- Project/job identity can be formalized, reducing stale-background-work bugs.
- The product can eventually have a cleaner packaging and update story.

Tradeoffs:

- The project gains TypeScript, Rust/Tauri, IPC, and sidecar lifecycle complexity.
- Packaging must account for a Python runtime and heavy ML dependencies.
- The migration must be phased to avoid losing the working app.

## Guardrails

- Keep `main` usable.
- Keep the PySide app until the new frontend reaches meaningful parity.
- Move domain logic out of UI code before replacing UI screens.
- Use small PRs with clear architecture boundaries.
- Prefer schemas, tests, and migration notes over implicit state.
