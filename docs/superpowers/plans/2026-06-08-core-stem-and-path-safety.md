# Core Stem And Path Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent unsafe stem/display names from becoming filesystem paths, export names, manifest paths, or zip archive entries.

**Architecture:** Introduce a stable filesystem-safe stem key while keeping the display name visible to users. Validate loaded manifests, sanitize generated output paths, and ensure archive entries cannot escape their intended folders.

**Tech Stack:** Python dataclasses, pathlib, zipfile, pytest.

---

## Files

- Modify: `src/pitchstems/separation.py`
- Modify: `src/pitchstems/transcription.py`
- Modify: `src/pitchstems/pipeline.py`
- Modify: `src/pitchstems/project_store.py`
- Modify: `src/pitchstems/editor_project.py`
- Modify: `src/pitchstems/gui_track_controls.py`
- Test: `tests/test_pipeline_storage.py`
- Test: `tests/test_project_store.py`
- Test: `tests/test_editor_project.py`

## Task 1: Add Safe Stem Keys

- [ ] **Step 1: Write failing tests for safe generated stem keys**

Add to `tests/test_pipeline_storage.py`:

```python
def test_midi_rerun_sanitizes_stem_output_names(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stem_path = project_dir / "stems" / "unsafe.wav"
    stem_path.parent.mkdir(parents=True)
    stem_path.write_bytes(b"stem")

    def fake_transcribe(stem_name, audio_path, output_dir, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        midi_path = output_dir / "unsafe.mid"
        midi_path.write_bytes(b"MThd")
        return pipeline.MidiResult(stem=stem_name, path=midi_path)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", fake_transcribe)
    monkeypatch.setattr(pipeline, "combine_midi_tracks", lambda _midi, path: path.write_bytes(b"MThd") or path)

    result = pipeline.process_midi_from_stems(
        project_dir=project_dir,
        input_stem="song",
        normalized_audio=None,
        source_audio=stem_path,
        stems=[pipeline.StemResult(name="../Vocals:Lead", path=stem_path)],
        midi_policy="all",
        create_zip=True,
    )

    assert result.midi_files[0].path.relative_to(project_dir).parts[:2] == ("midi", "vocals-lead")
    assert (project_dir / "export" / "vocals-lead.mid").exists()
    with zipfile.ZipFile(result.zip_path) as archive:
        assert "midi/vocals-lead.mid" in archive.namelist()
        assert all(".." not in Path(name).parts for name in archive.namelist())
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_midi_rerun_sanitizes_stem_output_names -q`

Expected: FAIL because stem display names are currently used directly.

- [ ] **Step 2: Add safe key helper and dataclass fields**

In `src/pitchstems/separation.py`, extend `StemResult` and add a helper:

```python
@dataclass(frozen=True)
class StemResult:
    name: str
    path: Path
    stem_id: str | None = None

    @property
    def safe_key(self) -> str:
        return self.stem_id or safe_stem_key(self.name)


def safe_stem_key(value: str) -> str:
    cleaned = []
    previous_dash = False
    for character in value.strip().lower():
        if character.isalnum():
            cleaned.append(character)
            previous_dash = False
        elif not previous_dash:
            cleaned.append("-")
            previous_dash = True
    key = "".join(cleaned).strip("-")
    return key or "stem"
```

In `src/pitchstems/transcription.py`, extend `MidiResult`:

```python
@dataclass(frozen=True)
class MidiResult:
    stem: str
    path: Path
    stem_id: str | None = None

    @property
    def safe_key(self) -> str:
        from pitchstems.separation import safe_stem_key

        return self.stem_id or safe_stem_key(self.stem)
```

- [ ] **Step 3: Use safe keys in MIDI staging, exports, and zips**

Update `process_midi_from_stems()` in `src/pitchstems/pipeline.py` so per-stem output directories and export names use `stem.safe_key`:

```python
midi = transcribe_stem_to_midi(
    stem.name,
    stem.path,
    staged_midi_dir / stem.safe_key,
    skip_percussion=skip_percussion,
    options=midi_options,
    log=log,
)
if midi:
    midi_files.append(MidiResult(midi.stem, midi.path, stem.safe_key))
```

Update final paths and exports:

```python
final_midi_files = [
    MidiResult(midi.stem, midi_dir / midi.path.relative_to(staged_midi_dir), midi.safe_key)
    for midi in midi_files
]
for midi in midi_files:
    shutil.copy2(midi.path, staged_export_dir / f"{midi.safe_key}.mid")
generated_export_midi = {f"{input_stem}_combined.mid"} | {f"{stem.safe_key}.mid" for stem in stems}
```

Update `_zip_project_outputs()` so archive paths use safe keys:

```python
archive.write(stem.path, Path("stems") / f"{stem.safe_key}{stem.path.suffix.lower() or '.wav'}")
archive.write(midi.path, Path("midi") / f"{midi.safe_key}.mid")
```

- [ ] **Step 4: Verify targeted test passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline_storage.py::test_midi_rerun_sanitizes_stem_output_names -q`

Expected: PASS.

## Task 2: Validate Manifest Stem And MIDI Names

- [ ] **Step 1: Write failing manifest validation tests**

Add to `tests/test_project_store.py`:

```python
def test_manifest_rejects_unsafe_stem_names(tmp_path: Path) -> None:
    project_dir = tmp_path / "unsafe.pitchstems"
    project_dir.mkdir()
    manifest_path = project_dir / "pitchstems.project.json"
    manifest_path.write_text(json.dumps({
        "format": "pitchstems-project",
        "format_version": 2,
        "created_at": "2026-06-08T00:00:00Z",
        "updated_at": "2026-06-08T00:00:00Z",
        "name": "unsafe",
        "source_audio": "audio/source.wav",
        "normalized_audio": "work/source.wav",
        "stems": [{"name": "../vocals", "path": "stems/vocals.wav"}],
        "midi_files": [],
        "combined_midi": None,
        "zip_path": None,
        "settings": {},
        "editor": {},
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe stem name"):
        load_project_manifest(manifest_path)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py::test_manifest_rejects_unsafe_stem_names -q`

Expected: FAIL because names are not validated yet.

- [ ] **Step 2: Add validation helpers**

In `src/pitchstems/project_store.py`, import `safe_stem_key` and add:

```python
def _validate_safe_display_name(path: Path, value: str, label: str) -> None:
    if safe_stem_key(value) != value.strip().lower():
        raise ValueError(f"{path} has unsafe {label}: {value}")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"{path} has unsafe {label}: {value}")
```

Call it inside stem and MIDI item validation:

```python
_validate_safe_display_name(path, item["name"], "stem name")
_validate_safe_display_name(path, item["stem"], "MIDI stem name")
```

If existing manifests may contain mixed-case names such as `Vocals`, use this less strict helper instead:

```python
def _validate_safe_display_name(path: Path, value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{path} has unsafe {label}: {value}")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError(f"{path} has unsafe {label}: {value}")
    if any(part in {".", ".."} for part in Path(value).parts):
        raise ValueError(f"{path} has unsafe {label}: {value}")
    if safe_stem_key(value) == "stem" and value.strip().lower() != "stem":
        raise ValueError(f"{path} has unsafe {label}: {value}")
```

Use the less strict version if current tests reveal valid legacy names.

- [ ] **Step 3: Verify manifest tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py -q`

Expected: PASS.

## Task 3: Persist Safe Keys Without Breaking Legacy Manifests

- [ ] **Step 1: Add manifest round-trip tests**

Add to `tests/test_project_store.py`:

```python
def test_manifest_saves_and_loads_stem_ids(tmp_path: Path) -> None:
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[StemResult("Vocals Lead", tmp_path / "song.pitchstems" / "stems" / "vocals.wav", "vocals-lead")],
        midi_files=[MidiResult("Vocals Lead", tmp_path / "song.pitchstems" / "midi" / "vocals-lead" / "x.mid", "vocals-lead")],
        combined_midi=None,
        zip_path=None,
        source_audio=tmp_path / "song.pitchstems" / "audio" / "song.wav",
    )

    save_project_manifest(result)
    manifest = load_project_manifest(result.project_dir)

    assert manifest["stems"][0]["stem_id"] == "vocals-lead"
    assert manifest["midi_files"][0]["stem_id"] == "vocals-lead"
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py::test_manifest_saves_and_loads_stem_ids -q`

Expected: FAIL.

- [ ] **Step 2: Write and read `stem_id` fields**

In `save_project_manifest()`, write:

```python
{"name": stem.name, "stem_id": stem.safe_key, "path": _relative_or_absolute(project_dir, stem.path)}
{"stem": midi.stem, "stem_id": midi.safe_key, "path": _relative_or_absolute(project_dir, midi.path)}
```

In `manifest_to_result()`, read:

```python
StemResult(name=item["name"], path=_resolve_project_path(project_dir, item["path"]), stem_id=item.get("stem_id"))
MidiResult(stem=item["stem"], path=_resolve_project_path(project_dir, item["path"]), stem_id=item.get("stem_id"))
```

- [ ] **Step 3: Verify storage and pipeline safety**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_project_store.py tests/test_pipeline_storage.py -q
.\scripts\check.ps1
```

Expected: PASS.

## Task 4: Commit Core Safety Work

- [ ] **Step 1: Review diff**

Run: `git diff -- src tests`

Expected: only stem/path safety files and tests changed.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src\pitchstems\separation.py src\pitchstems\transcription.py src\pitchstems\pipeline.py src\pitchstems\project_store.py src\pitchstems\editor_project.py src\pitchstems\gui_track_controls.py tests\test_pipeline_storage.py tests\test_project_store.py tests\test_editor_project.py
git commit -m "fix: sanitize stem output identifiers"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: covers unsafe stem names in filesystem paths, export names, manifest data, and zip entries.
- Placeholder scan: all tasks name exact files, tests, and commands.
- Type consistency: `stem_id` and `safe_key` are introduced on `StemResult` and `MidiResult` and used consistently.
