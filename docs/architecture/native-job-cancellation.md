# Native Job Cancellation

PitchStems cancellation is cooperative in the Python orchestration layer. The app checks
cancellation before and after expensive native model stages, but it does not interrupt
BS-RoFormer or Basic Pitch once those libraries are executing.

## Current Boundary

- `process_audio_file()` can stop between copy, normalization, separation, MIDI, and archive
  stages.
- `process_midi_from_stems()` can stop between stem transcriptions and before replacement of
  previous MIDI outputs.
- `separate_stems()` and `transcribe_to_midi()` are treated as native calls that either return,
  raise, or finish through their library-level behavior.

## User-Facing Behavior

When the user closes the app during processing, PitchStems requests cancellation, waits for the
current model stage to finish, and then closes. This avoids corrupting project folders or leaving
half-written replacement MIDI.

## Future Process-Based Strategy

The next architecture should run ML work in a separate job process or sidecar. Each job should have
a stable `job_id`, emit progress events, write outputs into a staging directory, and promote outputs
only after success. Cancellation can then terminate the process, delete the staging directory, and
leave the existing project unchanged.

## Future Boundary Requirements

Any process-based implementation must preserve the current project safety rule: write into a staging
project or staging output directory first, then promote outputs only after success. Cancellation may
terminate the process and delete staging data, but it must not remove or mutate the last successful
project manifest.

## Non-Goals

- Do not kill Python threads inside the current PySide process.
- Do not terminate model libraries mid-write without a staging boundary.
- Do not change existing `.pitchstems` project compatibility for cancellation alone.
