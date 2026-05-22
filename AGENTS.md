# PitchStems Agent Guide

PitchStems is a solo-developer, local-first desktop app. Work quickly, keep the project usable, and use the lightest process that still protects the work.

## Working Style

- Keep `main` stable and use short-lived `feature/*` or `fix/*` branches for meaningful work.
- Prefer small, reversible changes that can be tested and explained.
- Use focused checks while iterating; run the full project check before asking to commit, push, open a PR, merge, tag, or release.
- Avoid ceremony that does not reduce risk, save time, or clarify the work.
- Keep generated audio, stems, MIDI, exports, model weights, and user files out of git.
- Preserve the local-first posture and GPU-capable Windows workflow.

## Git And Approval

The agent may inspect, edit, test, create local branches, stage, and make sensible local checkpoint commits when that clearly protects work or keeps the project moving.

Ask for explicit user approval before pushing, opening or updating PRs, merging, tagging, releasing, or changing repo settings. Be extra careful with destructive git operations; avoid them unless the user explicitly asks.

When asking for approval, summarize the branch, changed files, checks run, proposed PR/release action, and any known risks.

## Checks

Use the project venv when available.

```powershell
.\scripts\check.ps1
```

Add flags only when relevant:

```powershell
.\scripts\check.ps1 -Gpu -GuiSmoke -Build
```

## Self-Improvement

Improve this guide when a recurring mistake, user preference, or repeated manual step becomes clear. Keep it short, general, and useful. Remove obsolete guidance instead of only appending more rules. Do not commit changes without user approval.
