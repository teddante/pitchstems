from __future__ import annotations

import sys
from pathlib import Path

import pitchstems.cli as cli
from pitchstems.pipeline import PipelineResult
from pitchstems.separation import SeparationOptions


def test_cli_quality_reaches_pipeline_without_default_separation_options(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")
    captured: dict[str, object] = {}

    def fake_process_audio_file(audio_file: Path, output_dir: Path, **kwargs):
        captured.update(kwargs)
        return PipelineResult(
            project_dir=output_dir / "song.pitchstems",
            normalized_audio=output_dir / "song.pitchstems" / "work" / "song.wav",
            stems=[],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=audio_file,
        )

    monkeypatch.setattr(cli, "process_audio_file", fake_process_audio_file)
    monkeypatch.setattr(sys, "argv", ["pitchstems", str(source), "--quality", "song-6-stem"])

    assert cli.main() == 0

    assert captured["quality"] == "song-6-stem"
    assert captured["separation_options"] is None


def test_cli_explicit_model_builds_separation_options(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")
    captured: dict[str, object] = {}

    def fake_process_audio_file(audio_file: Path, output_dir: Path, **kwargs):
        captured.update(kwargs)
        return PipelineResult(
            project_dir=output_dir / "song.pitchstems",
            normalized_audio=output_dir / "song.pitchstems" / "work" / "song.wav",
            stems=[],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=audio_file,
        )

    monkeypatch.setattr(cli, "process_audio_file", fake_process_audio_file)
    monkeypatch.setattr(sys, "argv", ["pitchstems", str(source), "--model", "bs_roformer_sw"])

    assert cli.main() == 0

    options = captured["separation_options"]
    assert isinstance(options, SeparationOptions)
    assert options.model_key == "bs_roformer_sw"
