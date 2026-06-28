from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "pitchstems"

RESULT_MODEL_IMPORTS = {
    "pitchstems.pipeline": {"PipelineResult"},
    "pitchstems.separation": {"StemResult"},
    "pitchstems.transcription": {"MidiResult"},
}


def test_result_model_consumers_use_neutral_model_module() -> None:
    offenders: list[str] = []
    for path in SRC_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module not in RESULT_MODEL_IMPORTS:
                continue
            forbidden_names = RESULT_MODEL_IMPORTS[node.module]
            for alias in node.names:
                if alias.name in forbidden_names:
                    offenders.append(f"{path.name}: {alias.name} from {node.module}")

    assert offenders == []


def test_processing_modules_keep_result_model_compatibility_aliases() -> None:
    from pitchstems import separation, transcription
    from pitchstems.pipeline_models import MidiResult, StemResult

    assert separation.StemResult is StemResult
    assert transcription.MidiResult is MidiResult
