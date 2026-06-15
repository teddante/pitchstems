# PitchStems Agent Guide

PitchStems is a solo-developer, local-first desktop app. Work quickly, keep the project usable, and use the lightest process that still protects the work.

## Working Style

- Keep `main` stable and commit directly to `main` by default to save time and tokens.
- Use short-lived branches, issues, or PRs only when explicitly requested, when remote collaboration/review is needed, or when risk is high enough that isolating the work clearly reduces danger.
- Prefer small, reversible changes that can be tested and explained.
- Use focused checks while iterating; run the full project check before asking to commit, push, open a PR, merge, tag, or release.
- Avoid ceremony that does not reduce risk, save time, or clarify the work.
- Optimize for useful progress per minute: keep context reads focused, batch independent inspections, avoid repeated slow commands, and choose the lightest check that proves the current change.
- Treat token and output volume as part of efficiency: summarize large visual/user inputs once, keep progress updates phase-level, batch related edits when safe, and avoid repeating long issue lists in goals and final summaries.
- Keep generated audio, stems, MIDI, exports, model weights, and user files out of git.
- Preserve the local-first posture and GPU-capable Windows workflow.

## Context And Output Efficiency

- Prefer bounded evidence over broad dumps. Use targeted `rg`, small file slices, `git diff --stat`, and per-file diffs only when they answer the current question.
- Keep command output short by default: cap search/list output, use concise test modes where available, and inspect failures before rerunning.
- Match commands to the active shell. In this Windows repo, prefer PowerShell-native commands or small Python helpers over Bash syntax that will need retrying.
- For repeated audits, reuse or create a small bounded script/helper for import graphs, module size counts, and duplicate-signal scans instead of rebuilding fragile one-off shell pipelines.
- When reviewing Codex threads or tool history, avoid including raw outputs unless needed; cap per-item output and do not re-ingest large inline images or base64 blobs after they have been summarized.
- For long implementation turns, report progress by phase: context gathered, edits underway, verification, and result. Avoid one update per tiny hunk unless the user needs that granularity.
- Run focused checks while iterating, especially `ruff`/targeted tests after import or test edits and focused `mypy` after new shared types/protocols. Then run one full required check once the diff is stable, and rerun it after production edits that could affect the result.

## Git And Autonomy

The agent may inspect, edit, test, stage, commit, and push directly to `main` when the change is coherent, checks pass, and the action is the normal efficient next step.

Prefer automation over ceremony. Avoid creating issues, branches, or pull requests for routine solo-developer work unless the user asks for them or the risk justifies the extra process.

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

Improve this guide when a recurring mistake, user preference, repeated manual step, or reliable efficiency gain becomes clear. Keep it short, general, and useful. Remove obsolete guidance instead of only appending more rules.

Favor recursive improvement that makes future work faster, clearer, safer, or more correct: better checks, smaller modules, clearer workflows, less duplicate effort, and fewer unnecessary prompts. Commit guide updates when they are coherent, low-risk, and aligned with the user's standing preferences.
