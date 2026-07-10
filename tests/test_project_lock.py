from pathlib import Path

import pytest

from pitchstems.project_lock import project_mutation_lock


def test_project_mutation_lock_rejects_concurrent_writer(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"

    with project_mutation_lock(project_dir):
        with pytest.raises(RuntimeError, match="already being modified"):
            with project_mutation_lock(project_dir):
                raise AssertionError("second writer unexpectedly acquired the project lock")
