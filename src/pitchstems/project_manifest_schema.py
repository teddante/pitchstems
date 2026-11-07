from __future__ import annotations

from pathlib import Path
from typing import Any

from pitchstems.filename_safety import safe_stem_key


PROJECT_FORMAT_VERSION = 2

def _validate_manifest(path: Path, manifest: dict[str, Any]) -> None:
    project_dir = path.parent.resolve()
    if not isinstance(manifest, dict):
        raise ValueError(f"{path} is not a PitchStems project")
    if manifest.get("format") != "pitchstems-project":
        raise ValueError(f"{path} is not a PitchStems project")
    try:
        format_version = int(manifest.get("format_version", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} has an invalid PitchStems project format version") from exc
    if format_version > PROJECT_FORMAT_VERSION:
        raise ValueError(f"{path} was created by a newer PitchStems project format")
    required_fields = {
        "normalized_audio": str,
        "stems": list,
        "midi_files": list,
    }
    for field_name, expected_type in required_fields.items():
        if not isinstance(manifest.get(field_name), expected_type):
            raise ValueError(f"{path} is missing required project field: {field_name}")
    _validate_generated_asset_entries(
        path,
        project_dir,
        manifest.get("stems", []),
        collection_field="stems",
        name_field="name",
        entry_label="stem",
        name_label="stem name",
    )
    _validate_generated_asset_entries(
        path,
        project_dir,
        manifest.get("midi_files", []),
        collection_field="midi_files",
        name_field="stem",
        entry_label="MIDI",
        name_label="MIDI stem name",
    )
    _validate_project_path_value(path, project_dir, manifest["normalized_audio"], "normalized_audio")
    _validate_optional_project_paths(path, project_dir, manifest)


def _validate_generated_asset_entries(
    manifest_path: Path,
    project_dir: Path,
    entries: list[Any],
    *,
    collection_field: str,
    name_field: str,
    entry_label: str,
    name_label: str,
) -> None:
    seen_stem_ids: set[str] = set()
    for index, item in enumerate(entries):
        if (
            not isinstance(item, dict)
            or not _non_empty_string(item.get(name_field))
            or not _non_empty_string(item.get("path"))
        ):
            raise ValueError(f"{manifest_path} has an invalid {entry_label} entry at index {index}")
        _validate_safe_display_name(manifest_path, item[name_field], name_label)
        stem_id = item.get("stem_id")
        if stem_id is not None and not _non_empty_string(stem_id):
            raise ValueError(
                f"{manifest_path} has an invalid {entry_label} stem_id at index {index}"
            )
        resolved_stem_id = stem_id if isinstance(stem_id, str) else safe_stem_key(item[name_field])
        if resolved_stem_id != safe_stem_key(resolved_stem_id):
            raise ValueError(
                f"{manifest_path} has an unsafe {entry_label} stem_id at index {index}: "
                f"{resolved_stem_id}"
            )
        unique_key = resolved_stem_id.casefold()
        if unique_key in seen_stem_ids:
            raise ValueError(
                f"{manifest_path} has a duplicate {entry_label} stem_id: {resolved_stem_id}"
            )
        seen_stem_ids.add(unique_key)
        _validate_project_path_value(
            manifest_path,
            project_dir,
            item["path"],
            f"{collection_field}[{index}].path",
        )


def _validate_optional_project_paths(
    manifest_path: Path,
    project_dir: Path,
    manifest: dict[str, Any],
) -> None:
    for field_name in ("source_audio", "combined_midi", "zip_path"):
        value = manifest.get(field_name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{manifest_path} has an invalid project path field: {field_name}")
        if value:
            _validate_project_path_value(
                manifest_path,
                project_dir,
                value,
                field_name,
                allow_external_absolute=field_name == "source_audio",
            )


def _validate_project_path_value(
    manifest_path: Path,
    project_dir: Path,
    value: str,
    field_name: str,
    *,
    allow_external_absolute: bool = False,
) -> None:
    if not value.strip():
        raise ValueError(f"{manifest_path} has an empty project path field: {field_name}")
    value_path = Path(value)
    if value_path.is_absolute():
        if allow_external_absolute:
            return
        resolved = value_path.resolve()
    else:
        resolved = (project_dir / value_path).resolve()
    try:
        resolved.relative_to(project_dir)
    except ValueError as exc:
        raise ValueError(
            f"{manifest_path} has a project path outside the project folder: {field_name}"
        ) from exc


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_safe_display_name(path: Path, value: str, label: str) -> None:
    invalid_characters = set('<>:"/\\|?*')
    key = safe_stem_key(value)
    if (
        not value.strip()
        or value in {".", ".."}
        or any(part in {".", ".."} for part in Path(value).parts)
        or any(character in invalid_characters or ord(character) < 32 for character in value)
        or (key == "stem" and value.strip().lower() != "stem")
    ):
        raise ValueError(f"{path} has unsafe {label}: {value}")
