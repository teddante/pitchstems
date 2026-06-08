from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pitchstems.project_store import PROJECT_FILENAME


def normalize_recent_project_paths(value: Iterable[object] | str | None) -> list[Path]:
    if value is None:
        raw_paths: list[object] = []
    elif isinstance(value, str):
        raw_paths = [value]
    else:
        raw_paths = list(value)
    paths: list[Path] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        path = Path(str(raw_path)).expanduser()
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def recent_project_label(manifest_path: Path, max_parent_length: int = 46) -> str:
    project_dir = manifest_path.parent
    if manifest_path.name == PROJECT_FILENAME:
        return f"{project_dir.name}  ({short_path(project_dir.parent, max_parent_length)})"
    return f"{manifest_path.name}  ({short_path(manifest_path.parent, max_parent_length)})"


def short_path(path: Path, max_length: int = 46) -> str:
    text = str(path)
    if len(text) <= max_length:
        return text
    return f"...{text[-(max_length - 3):]}"


def remember_recent_project(
    current_paths: Iterable[Path],
    project_dir: Path,
    limit: int = 10,
) -> list[Path]:
    manifest = (project_dir / PROJECT_FILENAME).expanduser().resolve()
    recent = [path for path in current_paths if path.expanduser().resolve() != manifest]
    recent.insert(0, manifest)
    return recent[:limit]


def remove_recent_project(current_paths: Iterable[Path], manifest_path: Path) -> list[Path]:
    target = manifest_path.expanduser().resolve()
    return [path for path in current_paths if path.expanduser().resolve() != target]
