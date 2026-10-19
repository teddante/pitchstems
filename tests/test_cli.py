from __future__ import annotations

import sys
from pathlib import Path

import pitchstems.cli as cli
from pitchstems.model_catalog import DEFAULT_MODEL_KEY
from pitchstems.pipeline_models import PipelineResult
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


def _capture_process_audio_file(captured: dict[str, object]):
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

    return fake_process_audio_file


def test_cli_defaults_leave_separation_options_to_the_pipeline(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "process_audio_file", _capture_process_audio_file(captured))
    monkeypatch.setattr(sys, "argv", ["pitchstems", str(source)])

    assert cli.main() == 0

    assert captured["separation_options"] is None


def test_cli_stem_builds_separation_options(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "process_audio_file", _capture_process_audio_file(captured))
    monkeypatch.setattr(sys, "argv", ["pitchstems", str(source), "--stem", "bass"])

    assert cli.main() == 0

    options = captured["separation_options"]
    assert isinstance(options, SeparationOptions)
    assert options.model_key == DEFAULT_MODEL_KEY
    assert options.selected_stem == "bass"


def test_cli_reports_pipeline_errors_without_traceback(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")

    def failing_process_audio_file(*_args, **_kwargs):
        raise RuntimeError("Preflight failed: FFmpeg missing")

    monkeypatch.setattr(cli, "process_audio_file", failing_process_audio_file)
    monkeypatch.setattr(sys, "argv", ["pitchstems", str(source)])

    assert cli.main() == 1

    assert "Error: Preflight failed: FFmpeg missing" in capsys.readouterr().err


def test_cli_normalizes_unbounded_midi_frequency_limits(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"RIFF")
    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "process_audio_file", _capture_process_audio_file(captured))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pitchstems",
            str(source),
            "--minimum-frequency",
            "0",
            "--maximum-frequency",
            "-10",
        ],
    )

    assert cli.main() == 0

    options = captured["midi_options"]
    assert isinstance(options, MidiOptions)
    assert options.minimum_frequency is None
    assert options.maximum_frequency is None


def test_cli_download_model_defaults_to_sw6(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_download_model(model_key: str, **_kwargs):
        captured["model_key"] = model_key
        return tmp_path / "models"

    monkeypatch.setattr(cli, "download_model", fake_download_model)
    monkeypatch.setattr(sys, "argv", ["pitchstems", "--download-model"])

    assert cli.main() == 0

    assert captured["model_key"] == DEFAULT_MODEL_KEY
    assert "Cached in:" in capsys.readouterr().out


def test_cli_setup_repairs_runtime(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    class Result:
        ok = True

    def fake_run_setup(*, log):
        captured["log"] = log
        return Result()

    monkeypatch.setattr(cli, "run_setup", fake_run_setup)
    monkeypatch.setattr(cli, "format_setup_result", lambda _result: "setup ok")
    monkeypatch.setattr(sys, "argv", ["pitchstems", "--setup"])

    assert cli.main() == 0

    assert captured["log"] is print
    assert "setup ok" in capsys.readouterr().out
