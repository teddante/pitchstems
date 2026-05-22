# Security Policy

## Supported Versions

PitchStems is pre-1.0. Security fixes target the current `main` branch.

## Reporting a Vulnerability

Please report vulnerabilities privately through GitHub Security Advisories once
the repository is published.

If advisories are not enabled yet, contact the maintainer directly and avoid
posting exploit details in a public issue.

## Scope

Security-sensitive areas include:

- local file handling for dropped audio paths
- generated output paths and ZIP export
- dependency installation scripts
- model download paths and cache handling
- audio decoding through FFmpeg

PitchStems does not intentionally collect telemetry or upload user audio.
