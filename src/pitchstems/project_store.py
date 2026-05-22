from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions, MidiResult


PROJECT_FILENAME = "pitchstems.project.json"
PROJECT_FORMAT_VERSION = 1


def project_manifest_path(project_dir: Path) -> Path:
    return project_dir / PROJECT_FILENAME


def find_project_manifest(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_dir():
        manifest = project_manifest_path(path)
    else:
        manifest = path
    if manifest.name != PROJECT_FILENAME:
        raise ValueError(f"Not a PitchStems project manifest: {manifest}")
    if not manifest.exists():
        raise FileNotFoundError(manifest)
    return manifest


def save_project_manifest(
    result,
    separation_options: SeparationOptions | None = None,
    midi_options: MidiOptions | None = None,
    midi_stems: set[str] | None = None,
    generate_midi: bool | None = None,
    midi_policy: str | None = None,
    create_zip: bool | None = None,
    track_visibility: dict[str, bool] | None = None,
    track_audio_enabled: dict[str, bool] | None = None,
    track_audio_volume: dict[str, int] | None = None,
    track_midi_enabled: dict[str, bool] | None = None,
    track_midi_volume: dict[str, int] | None = None,
    playhead_seconds: float | None = None,
    chord_overrides: list[dict[str, Any]] | None = None,
) -> Path:
    project_dir = result.project_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = project_manifest_path(project_dir)
    existing = _read_json(manifest_path) if manifest_path.exists() else {}
    created_at = existing.get("created_at") or _now()
    source_audio = result.source_audio or _path_from_manifest(project_dir, existing.get("source_audio"))

    manifest = {
        "format": "pitchstems-project",
        "format_version": PROJECT_FORMAT_VERSION,
        "created_at": created_at,
        "updated_at": _now(),
        "name": project_dir.name.removesuffix(".pitchstems"),
        "source_audio": _relative_or_absolute(project_dir, source_audio),
        "normalized_audio": _relative_or_absolute(project_dir, result.normalized_audio),
        "stems": [
            {"name": stem.name, "path": _relative_or_absolute(project_dir, stem.path)}
            for stem in result.stems
        ],
        "midi_files": [
            {"stem": midi.stem, "path": _relative_or_absolute(project_dir, midi.path)}
            for midi in result.midi_files
        ],
        "combined_midi": _relative_or_absolute(project_dir, result.combined_midi),
        "zip_path": _relative_or_absolute(project_dir, result.zip_path),
        "settings": {
            "separation": _dataclass_dict(separation_options)
            or existing.get("settings", {}).get("separation", {}),
            "midi": _dataclass_dict(midi_options) or existing.get("settings", {}).get("midi", {}),
            "midi_stems": sorted(midi_stems) if midi_stems is not None else existing.get("settings", {}).get("midi_stems", []),
            "generate_midi": generate_midi if generate_midi is not None else existing.get("settings", {}).get("generate_midi"),
            "midi_policy": midi_policy or existing.get("settings", {}).get("midi_policy"),
            "create_zip": create_zip if create_zip is not None else existing.get("settings", {}).get("create_zip"),
        },
        "editor": {
            "track_visibility": track_visibility
            if track_visibility is not None
            else existing.get("editor", {}).get("track_visibility", {}),
            "track_audio_enabled": track_audio_enabled
            if track_audio_enabled is not None
            else existing.get("editor", {}).get("track_audio_enabled", {}),
            "track_audio_volume": track_audio_volume
            if track_audio_volume is not None
            else existing.get("editor", {}).get("track_audio_volume", {}),
            "track_midi_enabled": track_midi_enabled
            if track_midi_enabled is not None
            else existing.get("editor", {}).get("track_midi_enabled", {}),
            "track_midi_volume": track_midi_volume
            if track_midi_volume is not None
            else existing.get("editor", {}).get("track_midi_volume", {}),
            "playhead_seconds": playhead_seconds
            if playhead_seconds is not None
            else existing.get("editor", {}).get("playhead_seconds", 0.0),
            "chord_overrides": chord_overrides
            if chord_overrides is not None
            else existing.get("editor", {}).get("chord_overrides", []),
            "note_edits": existing.get("editor", {}).get("note_edits", []),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_pipeline_result(path: Path):
    manifest_path = find_project_manifest(path)
    project_dir = manifest_path.parent
    manifest = _read_json(manifest_path)
    _validate_manifest(manifest_path, manifest)

    from pitchstems.pipeline import PipelineResult

    return PipelineResult(
        project_dir=project_dir,
        normalized_audio=_resolve_project_path(project_dir, manifest.get("normalized_audio")),
        stems=[
            StemResult(name=item["name"], path=_resolve_project_path(project_dir, item["path"]))
            for item in manifest.get("stems", [])
        ],
        midi_files=[
            MidiResult(stem=item["stem"], path=_resolve_project_path(project_dir, item["path"]))
            for item in manifest.get("midi_files", [])
        ],
        combined_midi=_optional_project_path(project_dir, manifest.get("combined_midi")),
        zip_path=_optional_project_path(project_dir, manifest.get("zip_path")),
        source_audio=_optional_project_path(project_dir, manifest.get("source_audio")),
    )


def load_project_manifest(path: Path) -> dict[str, Any]:
    manifest_path = find_project_manifest(path)
    manifest = _read_json(manifest_path)
    _validate_manifest(manifest_path, manifest)
    return manifest


def _validate_manifest(path: Path, manifest: dict[str, Any]) -> None:
    if manifest.get("format") != "pitchstems-project":
        raise ValueError(f"{path} is not a PitchStems project")
    if int(manifest.get("format_version", 0)) > PROJECT_FORMAT_VERSION:
        raise ValueError(f"{path} was created by a newer PitchStems project format")


def _dataclass_dict(value) -> dict[str, Any]:
    if value is None:
        return {}
    if not is_dataclass(value):
        return {}
    data = asdict(value)
    return {key: _jsonable(item) for key, item in data.items() if key != "choice"}


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_or_absolute(project_dir: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    path = path.expanduser().resolve()
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def _resolve_project_path(project_dir: Path, value: str | None) -> Path:
    if not value:
        return project_dir
    path = Path(value)
    if path.is_absolute():
        return path
    return project_dir / path


def _optional_project_path(project_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    return _resolve_project_path(project_dir, value)


def _path_from_manifest(project_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    return _resolve_project_path(project_dir, value)
