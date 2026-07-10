import json
import os
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from mido import Message, MidiFile, MidiTrack

import pitchstems.pipeline as pipeline
from pitchstems.audio_clip import AudioClipRange
from pitchstems.pipeline import (
    _MidiWorkspace,
    _ProjectWorkspace,
    _package_pipeline_outputs,
    _prepare_source_audio_input,
    _project_dir,
    _remove_export_stem_copies,
    _remove_staging_dir,
    _save_pipeline_manifest,
    _safe_stem,
    _selected_midi_stem_keys,
    _zip_project_outputs,
    process_audio_file,
    process_midi_from_stems,
)
from pitchstems.pipeline_models import MidiResult, PipelineResult, StemResult
from pitchstems.project_store import save_project_manifest
from pitchstems.separation import SeparationOptions
from pitchstems.transcription import MidiOptions


@pytest.fixture(autouse=True)
def _pass_pipeline_preflight(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "run_preflight",
        lambda **_kwargs: SimpleNamespace(ok=True, failure_summary=lambda: ""),
    )


def _write_file(path: Path, content: bytes = b"placeholder") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_selected_midi_stem_keys_all_stems() -> None:
    assert _selected_midi_stem_keys(None) is None


def test_selected_midi_stem_keys_normalizes_explicit_selection() -> None:
    assert _selected_midi_stem_keys({"Bass", "DRUMS"}) == {"bass", "drums"}


def test_selected_midi_stem_keys_rejects_empty_explicit_selection() -> None:
    with pytest.raises(ValueError, match="Choose at least one stem"):
        _selected_midi_stem_keys(set())


def test_prepare_source_audio_input_copies_whole_file_import(tmp_path: Path) -> None:
    input_path = _write_file(tmp_path / "Song.MP3", b"audio")
    workspace = _ProjectWorkspace.from_input(tmp_path / "out", input_path)
    workspace.create_directories()

    project_source_audio, normalize_input = _prepare_source_audio_input(
        input_path,
        workspace,
        None,
    )

    assert project_source_audio == workspace.audio_dir / "Song.mp3"
    assert project_source_audio.read_bytes() == b"audio"
    assert normalize_input == project_source_audio


def test_prepare_source_audio_input_uses_original_for_clip_import(tmp_path: Path) -> None:
    input_path = _write_file(tmp_path / "Song.wav", b"audio")
    workspace = _ProjectWorkspace.from_input(tmp_path / "out", input_path)
    workspace.create_directories()
    source_clip = AudioClipRange(1.0, 4.0)

    project_source_audio, normalize_input = _prepare_source_audio_input(
        input_path,
        workspace,
        source_clip,
    )

    assert project_source_audio == workspace.audio_dir / "Song_clip.wav"
    assert not project_source_audio.exists()
    assert normalize_input == input_path


def _fake_normalize(_input_path, output_path, **_kwargs):
    return _write_file(output_path, b"wav")


def _fake_separate(
    _audio_path,
    output_dir,
    **_kwargs,
) -> list[StemResult]:
    return [StemResult("bass", _write_file(output_dir / "source_bass.wav", b"stem"))]


def _fake_song_separate(
    _audio_path,
    output_dir,
    **_kwargs,
) -> list[StemResult]:
    return [StemResult("bass", _write_file(output_dir / "song_bass.wav", b"stem"))]


def _fake_transcribe(stem_name, _audio_path, output_dir, **_kwargs):
    midi_path = output_dir / f"{stem_name}.mid"
    _write_midi(midi_path, 40)
    return MidiResult(stem_name, midi_path)


def test_zip_project_outputs_packages_canonical_assets_without_export_copies(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    stems_dir.mkdir(parents=True)
    midi_dir.mkdir(parents=True)
    export_dir.mkdir()

    stem_path = stems_dir / "song_bass.wav"
    midi_path = midi_dir / "song_bass.mid"
    combined_path = export_dir / "song_combined.mid"
    manifest_path = project_dir / "pitchstems.project.json"
    zip_path = project_dir / "song_pitchstems.zip"
    stem_path.write_bytes(b"stem")
    midi_path.write_bytes(b"midi")
    combined_path.write_bytes(b"combined")
    manifest_path.write_text("{}", encoding="utf-8")

    _zip_project_outputs(
        project_dir,
        [StemResult("bass", stem_path)],
        [MidiResult("bass", midi_path)],
        combined_path,
        zip_path,
    )

    assert zip_path.is_file()
    assert not (export_dir / stem_path.name).exists()
    with ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == [
            "midi/bass.mid",
            "midi/song_combined.mid",
            "stems/bass.wav",
        ]


def test_midi_rerun_sanitizes_stem_output_names(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stem_path = project_dir / "stems" / "unsafe.wav"
    stem_path.parent.mkdir(parents=True)
    stem_path.write_bytes(b"stem")

    def fake_transcribe(stem_name, _audio_path, output_dir, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        midi_path = output_dir / "unsafe.mid"
        midi_path.write_bytes(b"MThd")
        return pipeline.MidiResult(stem=stem_name, path=midi_path)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", fake_transcribe)

    def fake_combine(_midi, path):
        path.write_bytes(b"MThd")
        return path

    monkeypatch.setattr(
        pipeline,
        "combine_midi_tracks",
        fake_combine,
    )

    result = pipeline.process_midi_from_stems(
        project_dir=project_dir,
        input_stem="song",
        normalized_audio=None,
        source_audio=stem_path,
        stems=[pipeline.StemResult(name="../Vocals:Lead", path=stem_path)],
        midi_policy="all",
        create_zip=True,
    )

    assert result.midi_files[0].path.relative_to(project_dir).parts[:2] == (
        "midi",
        "vocals-lead",
    )
    assert (project_dir / "export" / "vocals-lead.mid").exists()
    with ZipFile(result.zip_path) as archive:
        assert "midi/vocals-lead.mid" in archive.namelist()
        assert all(".." not in Path(name).parts for name in archive.namelist())


def test_remove_export_stem_copies_only_deletes_known_duplicate_stems(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    export_dir = project_dir / "export"
    stems_dir.mkdir(parents=True)
    export_dir.mkdir()

    stem_path = stems_dir / "song_bass.wav"
    duplicate_path = export_dir / stem_path.name
    unrelated_wav = export_dir / "manual_export.wav"
    stem_path.write_bytes(b"canonical")
    duplicate_path.write_bytes(b"duplicate")
    unrelated_wav.write_bytes(b"keep")
    duplicate_path.write_bytes(stem_path.read_bytes())
    duplicate_stat = stem_path.stat()
    duplicate_path.touch()

    os.utime(duplicate_path, ns=(duplicate_stat.st_atime_ns, duplicate_stat.st_mtime_ns))

    _remove_export_stem_copies(export_dir, [StemResult("bass", stem_path)])

    assert stem_path.is_file()
    assert not duplicate_path.exists()
    assert unrelated_wav.is_file()


def test_remove_export_stem_copies_keeps_modified_same_name_export(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    export_dir = project_dir / "export"
    stems_dir.mkdir(parents=True)
    export_dir.mkdir()

    stem_path = stems_dir / "song_bass.wav"
    edited_export = export_dir / stem_path.name
    stem_path.write_bytes(b"canonical")
    edited_export.write_bytes(b"manual-edit")

    _remove_export_stem_copies(export_dir, [StemResult("bass", stem_path)])

    assert stem_path.is_file()
    assert edited_export.is_file()


def test_midi_rerun_zip_includes_current_manifest(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    source_path = project_dir / "audio" / "source.mp3"
    normalized_path = project_dir / "work" / "source.wav"
    stem_path = stems_dir / "song_bass.wav"
    for path in [source_path, normalized_path, stem_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    result = process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=normalized_path,
        stems=[StemResult("bass", stem_path)],
        source_audio=source_path,
        midi_stems={"bass"},
        create_zip=True,
    )

    assert result.zip_path is not None
    with ZipFile(result.zip_path) as archive:
        assert "pitchstems.project.json" not in archive.namelist()
    manifest = (project_dir / "pitchstems.project.json").read_text(encoding="utf-8")
    assert '"source_audio": "audio/source.mp3"' in manifest
    assert '"zip_path": "source_pitchstems.zip"' in manifest


def test_midi_rerun_result_preserves_existing_source_audio(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    source_path = project_dir / "audio" / "source.mp3"
    normalized_path = project_dir / "work" / "source.wav"
    stem_path = project_dir / "stems" / "song_bass.wav"
    for path in [source_path, normalized_path, stem_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
    save_project_manifest(
        PipelineResult(
            project_dir=project_dir,
            normalized_audio=normalized_path,
            stems=[StemResult("bass", stem_path)],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=source_path,
        )
    )

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    result = process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=normalized_path,
        stems=[StemResult("bass", stem_path)],
        midi_stems={"bass"},
        create_zip=False,
    )

    assert result.source_audio == source_path


def test_midi_rerun_result_preserves_existing_source_clip_metadata(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    source_path = project_dir / "audio" / "source_clip.wav"
    normalized_path = project_dir / "work" / "source.wav"
    stem_path = project_dir / "stems" / "song_bass.wav"
    clip = AudioClipRange(2.0, 8.5)
    for path in [source_path, normalized_path, stem_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
    save_project_manifest(
        PipelineResult(
            project_dir=project_dir,
            normalized_audio=normalized_path,
            stems=[StemResult("bass", stem_path)],
            midi_files=[],
            combined_midi=None,
            zip_path=None,
            source_audio=source_path,
            source_clip=clip,
        )
    )

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    result = process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=normalized_path,
        stems=[StemResult("bass", stem_path)],
        midi_stems={"bass"},
        create_zip=False,
    )

    assert result.source_audio == source_path
    assert result.source_clip == clip


def test_save_pipeline_manifest_passes_pipeline_options(monkeypatch, tmp_path: Path) -> None:
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )
    separation_options = SeparationOptions(device="cpu")
    midi_options = MidiOptions(onset_threshold=0.42)
    calls = []

    def fake_save_project_manifest(saved_result, **kwargs):
        calls.append((saved_result, kwargs))

    monkeypatch.setattr(pipeline, "save_project_manifest", fake_save_project_manifest)

    _save_pipeline_manifest(
        result,
        separation_options=separation_options,
        midi_options=midi_options,
        midi_stems={"bass"},
        generate_midi=False,
        midi_policy="none",
        create_zip=False,
    )

    assert calls == [
        (
            result,
            {
                "separation_options": separation_options,
                "midi_options": midi_options,
                "midi_stems": {"bass"},
                "generate_midi": False,
                "midi_policy": "none",
                "create_zip": False,
            },
        )
    ]


def test_package_pipeline_outputs_skips_when_zip_is_not_requested(monkeypatch, tmp_path: Path) -> None:
    result = PipelineResult(
        project_dir=tmp_path / "song.pitchstems",
        normalized_audio=tmp_path / "song.pitchstems" / "work" / "song.wav",
        stems=[],
        midi_files=[],
        combined_midi=None,
        zip_path=None,
    )
    calls = []
    monkeypatch.setattr(pipeline, "_zip_project_outputs", lambda *args: calls.append(args))

    assert _package_pipeline_outputs(result) is None
    assert calls == []


def test_package_pipeline_outputs_forwards_result_assets(monkeypatch, tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stem = StemResult("bass", project_dir / "stems" / "bass.wav")
    midi = MidiResult("bass", project_dir / "midi" / "bass.mid")
    combined = project_dir / "export" / "song_combined.mid"
    zip_path = project_dir / "song_pitchstems.zip"
    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=project_dir / "work" / "song.wav",
        stems=[stem],
        midi_files=[midi],
        combined_midi=combined,
        zip_path=zip_path,
    )
    calls = []

    def fake_zip_project_outputs(*args):
        calls.append(args)
        return zip_path

    monkeypatch.setattr(pipeline, "_zip_project_outputs", fake_zip_project_outputs)

    assert _package_pipeline_outputs(result) == zip_path
    assert calls == [(project_dir, [stem], [midi], combined, zip_path)]


def test_midi_rerun_keeps_existing_outputs_when_transcription_fails(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    stem_path = stems_dir / "song_bass.wav"
    old_midi = midi_dir / "old.mid"
    old_export = export_dir / "bass.mid"
    old_combined = export_dir / "source_combined.mid"
    for path in [stem_path, old_midi, old_export, old_combined]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    def failing_transcribe(*_args, **_kwargs):
        raise RuntimeError("basic pitch failed")

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", failing_transcribe)

    try:
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[StemResult("bass", stem_path)],
            midi_stems={"bass"},
            create_zip=False,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected MIDI rerun failure")

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"
    assert not (project_dir / "midi.tmp").exists()
    assert not (project_dir / "export.tmp").exists()
    assert old_combined.read_bytes() == b"old"
    assert not (project_dir / "midi.tmp").exists()
    assert not (project_dir / "export.tmp").exists()


def test_midi_rerun_rejects_empty_explicit_stem_selection_without_replacing_outputs(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "song.pitchstems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    old_midi = midi_dir / "old.mid"
    old_export = export_dir / "bass.mid"
    for path in [old_midi, old_export]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    try:
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[],
            midi_stems=set(),
            create_zip=False,
        )
    except ValueError as exc:
        assert "Choose at least one stem" in str(exc)
    else:
        raise AssertionError("Expected empty MIDI stem selection to be rejected")

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"


def test_midi_rerun_validates_staged_paths_before_replacing_existing_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    stem_path = stems_dir / "song_bass.wav"
    old_midi = midi_dir / "old.mid"
    old_export = export_dir / "bass.mid"
    outside_midi = tmp_path / "outside.mid"
    for path in [stem_path, old_midi, old_export]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")
    _write_midi(outside_midi, 40)

    def bad_transcribe(stem_name, _audio_path, _output_dir, **_kwargs):
        return MidiResult(stem_name, outside_midi)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", bad_transcribe)

    try:
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[StemResult("bass", stem_path)],
            midi_stems={"bass"},
            create_zip=False,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected staged path validation failure")

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"
    assert not (project_dir / "midi.tmp").exists()
    assert not (project_dir / "export.tmp").exists()


def test_midi_rerun_keeps_unrelated_export_midi_files(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    stem_path = stems_dir / "song_bass.wav"
    manual_midi = project_dir / "export" / "manual_edit.mid"
    old_generated = project_dir / "export" / "bass.mid"
    for path in [stem_path, manual_midi, old_generated]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    result = process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=None,
        stems=[StemResult("bass", stem_path)],
        midi_stems={"bass"},
        create_zip=False,
    )

    assert result.midi_files
    assert manual_midi.read_bytes() == b"old"
    assert old_generated.read_bytes() != b"old"


def test_midi_rerun_clears_stale_midi_preview_cache(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    stem_path = stems_dir / "song_bass.wav"
    preview = project_dir / "editor" / "midi-preview" / "bass_midi_preview.wav"
    for path in [stem_path, preview]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=None,
        stems=[StemResult("bass", stem_path)],
        midi_stems={"bass"},
        create_zip=False,
    )

    assert not preview.exists()


def test_midi_rerun_does_not_fail_if_preview_cache_cleanup_is_locked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    stem_path = stems_dir / "song_bass.wav"
    stem_path.parent.mkdir(parents=True, exist_ok=True)
    stem_path.write_bytes(b"old")

    real_remove_staging_dir = pipeline._remove_staging_dir

    def locked_preview_cache(path, project_root=None):
        if path == project_dir / "editor" / "midi-preview":
            raise PermissionError("preview in use")
        return real_remove_staging_dir(path, project_root)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)
    monkeypatch.setattr(pipeline, "_remove_staging_dir", locked_preview_cache)

    result = process_midi_from_stems(
        project_dir=project_dir,
        input_stem="source",
        normalized_audio=None,
        stems=[StemResult("bass", stem_path)],
        midi_stems={"bass"},
        create_zip=False,
    )

    assert result.midi_files


def test_midi_rerun_cancellation_preserves_existing_outputs(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stem_path = project_dir / "stems" / "song_bass.wav"
    old_midi = project_dir / "midi" / "bass" / "old.mid"
    old_export = project_dir / "export" / "bass.mid"
    for path in [stem_path, old_midi, old_export]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)

    with pytest.raises(pipeline.PipelineCancelledError):
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[StemResult("bass", stem_path)],
            midi_stems={"bass"},
            create_zip=False,
            cancelled=lambda: True,
        )

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"
    assert not (project_dir / "midi.tmp").exists()
    assert not (project_dir / "export.tmp").exists()


def test_remove_staging_dir_rejects_project_root(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    project_dir.mkdir()

    with pytest.raises(ValueError, match="must not be the project root"):
        _remove_staging_dir(project_dir, project_dir)

    assert project_dir.exists()


def test_remove_staging_dir_rejects_paths_outside_project(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    outside_dir = tmp_path / "outside.tmp"
    project_dir.mkdir()
    outside_dir.mkdir()

    with pytest.raises(ValueError, match="must stay inside the project folder"):
        _remove_staging_dir(outside_dir, project_dir)

    assert outside_dir.exists()


def test_remove_staging_dir_requires_project_context(tmp_path: Path) -> None:
    staging_dir = tmp_path / "midi.tmp"
    staging_dir.mkdir()

    with pytest.raises(ValueError, match="project_dir is required"):
        _remove_staging_dir(staging_dir)

    assert staging_dir.exists()


def test_remove_staging_dir_rejects_non_project_workspace(tmp_path: Path) -> None:
    project_dir = tmp_path / "plain-folder"
    staging_dir = project_dir / "midi.tmp"
    staging_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="must be a PitchStems project"):
        _remove_staging_dir(staging_dir, project_dir)

    assert staging_dir.exists()


def test_midi_rerun_restores_previous_outputs_if_replacement_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_dir = tmp_path / "song.pitchstems"
    stems_dir = project_dir / "stems"
    midi_dir = project_dir / "midi" / "bass"
    export_dir = project_dir / "export"
    stem_path = stems_dir / "song_bass.wav"
    old_midi = midi_dir / "old.mid"
    old_export = export_dir / "bass.mid"
    old_combined = export_dir / "source_combined.mid"
    for path in [stem_path, old_midi, old_export, old_combined]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")

    real_move = pipeline.shutil.move

    def flaky_move(source, destination, *args, **kwargs):
        if Path(source).name == "midi.tmp":
            raise OSError("simulated replace failure")
        return real_move(source, destination, *args, **kwargs)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)
    monkeypatch.setattr(pipeline.shutil, "move", flaky_move)

    try:
        process_midi_from_stems(
            project_dir=project_dir,
            input_stem="source",
            normalized_audio=None,
            stems=[StemResult("bass", stem_path)],
            midi_stems={"bass"},
            create_zip=False,
        )
    except OSError:
        pass
    else:
        raise AssertionError("Expected MIDI replacement failure")

    assert old_midi.read_bytes() == b"old"
    assert old_export.read_bytes() == b"old"
    assert old_combined.read_bytes() == b"old"
    assert not (project_dir / "midi.backup.tmp").exists()
    assert not (project_dir / "export.backup.tmp").exists()


def test_full_pipeline_packages_once_after_final_manifest(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    zip_calls = 0

    real_zip_project_outputs = pipeline._zip_project_outputs

    def counting_zip(*args, **kwargs):
        nonlocal zip_calls
        zip_calls += 1
        return real_zip_project_outputs(*args, **kwargs)

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_separate)
    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", _fake_transcribe)
    monkeypatch.setattr(pipeline, "_zip_project_outputs", counting_zip)

    result = process_audio_file(input_path, tmp_path / "out", midi_stems={"bass"}, create_zip=True)

    assert zip_calls == 1
    assert result.zip_path is not None
    with ZipFile(result.zip_path) as archive:
        assert "pitchstems.project.json" not in archive.namelist()
    manifest = (result.project_dir / "pitchstems.project.json").read_text(encoding="utf-8")
    assert '"source_audio": "audio/source.mp3"' in manifest
    assert '"zip_path": "source_pitchstems.zip"' in manifest


def test_full_pipeline_zip_failure_preserves_success_manifest(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_song_separate)
    monkeypatch.setattr(
        pipeline,
        "_zip_project_outputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("zip failed")),
    )

    with pytest.raises(RuntimeError, match="zip failed"):
        pipeline.process_audio_file(source, tmp_path / "out", generate_midi=False, create_zip=True)

    manifests = list((tmp_path / "out").glob("*.pitchstems/pitchstems.project.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest.get("status") != "failed"
    assert manifest["stems"] == [{"name": "bass", "stem_id": "bass", "path": "stems/song_bass.wav"}]
    assert manifest["midi_files"] == []


def test_full_pipeline_fails_before_project_creation_when_preflight_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(
        pipeline,
        "run_preflight",
        lambda **_kwargs: SimpleNamespace(
            ok=False,
            failure_summary=lambda: "FFmpeg: missing",
        ),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="Preflight failed: FFmpeg: missing"):
        pipeline.process_audio_file(source, tmp_path / "out")

    assert not list((tmp_path / "out").glob("*.pitchstems"))


def test_failed_full_pipeline_writes_failed_manifest(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(
        pipeline,
        "separate_stems",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("native failed")),
    )

    with pytest.raises(RuntimeError, match="native failed"):
        pipeline.process_audio_file(source, tmp_path / "out")

    manifests = list((tmp_path / "out").glob("*.pitchstems/pitchstems.project.json"))
    assert manifests
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "native failed" in manifest["last_error"]


def test_full_pipeline_cancellation_removes_partial_new_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    should_cancel = False

    def fake_separate(_audio_path, output_dir, **_kwargs):
        nonlocal should_cancel
        stem_path = _write_file(output_dir / "source_bass.wav", b"stem")
        should_cancel = True
        return [StemResult("bass", stem_path)]

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", fake_separate)

    with pytest.raises(pipeline.PipelineCancelledError):
        process_audio_file(
            input_path,
            tmp_path / "out",
            generate_midi=False,
            create_zip=False,
            cancelled=lambda: should_cancel,
        )

    assert not list((tmp_path / "out").glob("*.pitchstems"))


def test_full_pipeline_reports_created_project_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    created_dirs: list[Path] = []

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_separate)

    result = process_audio_file(
        input_path,
        tmp_path / "out",
        generate_midi=False,
        create_zip=False,
        project_created=created_dirs.append,
    )

    assert created_dirs == [result.project_dir]
    assert result.project_dir.exists()


def test_full_pipeline_clip_processes_small_wav_and_records_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"large audio")
    clip = AudioClipRange(12.0, 24.5)
    normalize_calls = []

    def fake_normalize(input_arg, output_path, **kwargs):
        normalize_calls.append((input_arg, output_path, kwargs.get("clip_range")))
        return _write_file(output_path, b"clipped wav")

    monkeypatch.setattr(pipeline, "normalize_to_wav", fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_separate)
    monkeypatch.setattr(
        pipeline,
        "_copy_source_audio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("full source copied")),
    )

    result = process_audio_file(
        input_path,
        tmp_path / "out",
        generate_midi=False,
        create_zip=False,
        source_clip=clip,
    )
    manifest = json.loads((result.project_dir / "pitchstems.project.json").read_text(encoding="utf-8"))

    assert normalize_calls == [(input_path.resolve(), result.normalized_audio, clip)]
    assert result.source_audio == result.project_dir / "audio" / "source_clip.wav"
    assert result.source_audio.read_bytes() == b"clipped wav"
    assert result.source_audio.samefile(result.normalized_audio)
    assert result.source_clip == clip
    assert manifest["source_audio"] == "audio/source_clip.wav"
    assert "original_source_audio" not in manifest["settings"]["source_clip"]
    assert manifest["settings"]["source_clip"]["start_seconds"] == 12.0
    assert manifest["settings"]["source_clip"]["end_seconds"] == 24.5


def test_full_pipeline_logs_deferred_cancellation_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    messages: list[str] = []

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_separate)

    process_audio_file(
        input_path,
        tmp_path / "out",
        generate_midi=False,
        create_zip=False,
        log=messages.append,
        cancelled=lambda: False,
    )

    assert "Cancellation will take effect between native model stages." in messages


def test_project_dir_avoids_same_second_name_collision(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"audio")
    first = _project_dir(tmp_path, audio_path)
    first.mkdir()

    second = _project_dir(tmp_path, audio_path)

    assert second != first
    assert second.name.endswith("-2.pitchstems")


def test_project_workspace_names_and_creates_pipeline_directories(tmp_path: Path) -> None:
    audio_path = tmp_path / "Song Title!.mp3"
    audio_path.write_bytes(b"audio")

    workspace = _ProjectWorkspace.from_input(tmp_path / "out", audio_path)
    workspace.create_directories()

    assert workspace.input_stem == "Song_Title"
    assert workspace.audio_dir == workspace.project_dir / "audio"
    assert workspace.work_dir == workspace.project_dir / "work"
    assert workspace.stems_dir == workspace.project_dir / "stems"
    assert workspace.midi_dir == workspace.project_dir / "midi"
    assert workspace.export_dir == workspace.project_dir / "export"
    assert workspace.normalized_audio == workspace.work_dir / "Song_Title.wav"
    assert workspace.zip_path == workspace.project_dir / "Song_Title_pitchstems.zip"
    assert all(
        path.is_dir()
        for path in [
            workspace.audio_dir,
            workspace.work_dir,
            workspace.stems_dir,
            workspace.midi_dir,
            workspace.export_dir,
        ]
    )


def test_project_workspace_atomically_reserves_distinct_directories(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"audio")

    first = _ProjectWorkspace.from_input(tmp_path / "out", audio_path)
    second = _ProjectWorkspace.from_input(tmp_path / "out", audio_path)

    assert first.project_dir != second.project_dir
    assert first.project_dir.is_dir()
    assert second.project_dir.is_dir()


def test_midi_workspace_names_rerun_directories(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"

    workspace = _MidiWorkspace.from_project(project_dir, "Song Title!")

    assert workspace.project_dir == project_dir
    assert workspace.input_stem == "Song_Title"
    assert workspace.midi_dir == project_dir / "midi"
    assert workspace.export_dir == project_dir / "export"
    assert workspace.staged_midi_dir == project_dir / "midi.tmp"
    assert workspace.staged_export_dir == project_dir / "export.tmp"
    assert workspace.backup_midi_dir == project_dir / "midi.backup.tmp"
    assert workspace.backup_export_dir == project_dir / "export.backup.tmp"
    assert workspace.transaction_path == project_dir / ".midi-transaction.json"
    assert workspace.normalized_audio == project_dir / "work" / "Song_Title.wav"
    assert workspace.zip_path == project_dir / "Song_Title_pitchstems.zip"


def test_midi_transaction_recovery_restores_backups_and_removes_new_outputs(
    tmp_path: Path,
) -> None:
    workspace = _MidiWorkspace.from_project(tmp_path / "song.pitchstems", "song")
    old_midi = _write_file(workspace.backup_midi_dir / "bass" / "old.mid", b"old-midi")
    _write_file(workspace.midi_dir / "bass" / "new.mid", b"new-midi")
    _write_file(workspace.backup_export_dir / "bass.mid", b"old-export")
    _write_file(workspace.export_dir / "bass.mid", b"new-export")
    new_only = _write_file(workspace.export_dir / "song_combined.mid", b"new-combined")
    pipeline._write_midi_transaction(
        workspace,
        "installed",
        {"bass.mid", "song_combined.mid"},
        True,
    )

    pipeline._recover_midi_transaction(workspace)

    assert (workspace.midi_dir / "bass" / old_midi.name).read_bytes() == b"old-midi"
    assert (workspace.export_dir / "bass.mid").read_bytes() == b"old-export"
    assert not new_only.exists()
    assert not workspace.transaction_path.exists()
    assert not workspace.backup_midi_dir.exists()
    assert not workspace.backup_export_dir.exists()


def test_committed_midi_transaction_recovery_keeps_new_outputs(tmp_path: Path) -> None:
    workspace = _MidiWorkspace.from_project(tmp_path / "song.pitchstems", "song")
    new_midi = _write_file(workspace.midi_dir / "bass" / "new.mid", b"new")
    _write_file(workspace.backup_midi_dir / "bass" / "old.mid", b"old")
    pipeline._write_midi_transaction(workspace, "committed", {"bass.mid"}, True)

    pipeline._recover_midi_transaction(workspace)

    assert new_midi.read_bytes() == b"new"
    assert not workspace.backup_midi_dir.exists()
    assert not workspace.transaction_path.exists()


def test_pipeline_uses_bounded_safe_names_for_long_audio_files(tmp_path: Path, monkeypatch) -> None:
    long_stem = "YTDown_YouTube_" + ("Very-Long-Title_" * 6)
    input_path = tmp_path / f"{long_stem}.mp3"
    input_path.write_bytes(b"audio")

    monkeypatch.setattr(pipeline, "normalize_to_wav", _fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", _fake_separate)

    result = process_audio_file(input_path, tmp_path / "out", generate_midi=False, create_zip=True)
    safe_stem = _safe_stem(input_path.stem)

    assert len(safe_stem) <= 80
    assert result.project_dir.name.startswith(safe_stem)
    assert result.source_audio == result.project_dir / "audio" / f"{safe_stem}.mp3"
    assert result.normalized_audio == result.project_dir / "work" / f"{safe_stem}.wav"
    assert result.zip_path == result.project_dir / f"{safe_stem}_pitchstems.zip"
    assert max(len(part) for part in result.project_dir.parts) <= 110


def test_safe_stem_avoids_empty_and_windows_reserved_names() -> None:
    assert _safe_stem("...") == "audio"
    assert _safe_stem("CON") == "audio_CON"
    assert _safe_stem("nul") == "audio_nul"
    assert _safe_stem("COM1") == "audio_COM1"
    assert _safe_stem("song?title") == "song_title"


def _write_midi(path: Path, note: int) -> None:
    midi = MidiFile()
    track = MidiTrack()
    track.append(Message("note_on", note=note, velocity=64, time=0))
    track.append(Message("note_off", note=note, velocity=0, time=120))
    midi.tracks.append(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)
