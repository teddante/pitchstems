# PitchStems Agent Guide

PitchStems is a solo-developer, local-first desktop app. Work quickly, keep the project usable, and use the lightest process that still protects the work.

## Working Style

- Keep `main` stable and use short-lived `feature/*` or `fix/*` branches for meaningful work.
- Prefer small, reversible changes that can be tested and explained.
- Use focused checks while iterating; run the full project check before asking to commit, push, open a PR, merge, tag, or release.
- Avoid ceremony that does not reduce risk, save time, or clarify the work.
- Keep generated audio, stems, MIDI, exports, model weights, and user files out of git.
- Preserve the local-first posture and GPU-capable Windows workflow.

## Git And Autonomy

The agent may inspect, edit, test, branch, stage, commit, push branches, and open/update pull requests when the change is coherent, checks pass, and the action is the normal efficient next step.

Prefer automation over ceremony. If the next GitHub step is low-risk and clearly recommended, do it.

Pause and ask first for destructive git operations, force-pushes, branch deletion with unmerged work, merge conflict choices that could discard work, public releases/tags, package publishing, repo setting changes, secrets, or anything where confidence is low.

When acting autonomously, summarize what was done, checks run, branch/PR/release links, and any known risks.

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
