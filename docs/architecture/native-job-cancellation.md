# Native Job Cancellation

PitchStems uses different cancellation boundaries for GUI and CLI execution.

## Current Boundary

- GUI full-pipeline and MIDI-rerun jobs execute in a child process.
- GUI Cancel terminates that child process, so native BS-RoFormer or Basic Pitch work can stop without waiting for the native call to return.
- CLI runs still execute in one process and remain cooperative between orchestration steps.
- `process_audio_file()` can report the newly created project folder to the parent process before native model work starts.
- `process_midi_from_stems()` still writes MIDI reruns through staging directories before promoting outputs.

## Cleanup Rules

For a cancelled GUI full-pipeline run, the parent process removes the recorded new project directory only when all of these are true:

- the path is inside the requested output root
- the path is not the output root itself
- the path has the `.pitchstems` suffix
- the path is not a symlink

For a cancelled GUI MIDI rerun, the existing project is not deleted. The MIDI stage uses temporary staging folders and only promotes outputs after normal success; a later rerun resets stale staging folders before starting.

## User-Facing Behavior

When the user cancels processing or closes the app during processing, PitchStems requests cancellation and terminates the active processing child. Stale worker messages remain token-filtered, so old results cannot replace the currently open project.

## Non-Goals

- Do not kill Python threads inside the PySide process.
- Do not remove an existing `.pitchstems` project because a MIDI rerun was cancelled.
- Do not change existing `.pitchstems` project compatibility for cancellation alone.
