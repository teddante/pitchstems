import os
from pathlib import Path
from zipfile import ZipFile

from mido import Message, MidiFile, MidiTrack

import pitchstems.pipeline as pipeline
from pitchstems.pipeline import (
    _project_dir,
    _remove_export_stem_copies,
    _zip_project_outputs,
    process_audio_file,
    process_midi_from_stems,
)
from pitchstems.separation import StemResult
from pitchstems.transcription import MidiResult


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
            "pitchstems.project.json",
            "stems/song_bass.wav",
        ]


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

    def fake_transcribe(stem_name, _audio_path, output_dir, **_kwargs):
        midi_path = output_dir / f"{stem_name}.mid"
        _write_midi(midi_path, 40)
        return MidiResult(stem_name, midi_path)

    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", fake_transcribe)

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
        manifest = archive.read("pitchstems.project.json").decode("utf-8")
    assert '"source_audio": "audio/source.mp3"' in manifest
    assert '"zip_path": "source_pitchstems.zip"' in manifest


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
    assert old_combined.read_bytes() == b"old"
    assert not (project_dir / "midi.tmp").exists()
    assert not (project_dir / "export.tmp").exists()


def test_full_pipeline_packages_once_after_final_manifest(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "source.mp3"
    input_path.write_bytes(b"audio")
    zip_calls = 0

    def fake_normalize(_input_path, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"wav")
        return output_path

    def fake_separate(_audio_path, output_dir, **_kwargs):
        stem_path = output_dir / "source_bass.wav"
        stem_path.parent.mkdir(parents=True, exist_ok=True)
        stem_path.write_bytes(b"stem")
        return [StemResult("bass", stem_path)]

    def fake_transcribe(stem_name, _audio_path, output_dir, **_kwargs):
        midi_path = output_dir / f"{stem_name}.mid"
        _write_midi(midi_path, 40)
        return MidiResult(stem_name, midi_path)

    real_zip_project_outputs = pipeline._zip_project_outputs

    def counting_zip(*args, **kwargs):
        nonlocal zip_calls
        zip_calls += 1
        return real_zip_project_outputs(*args, **kwargs)

    monkeypatch.setattr(pipeline, "normalize_to_wav", fake_normalize)
    monkeypatch.setattr(pipeline, "separate_stems", fake_separate)
    monkeypatch.setattr(pipeline, "transcribe_stem_to_midi", fake_transcribe)
    monkeypatch.setattr(pipeline, "_zip_project_outputs", counting_zip)

    result = process_audio_file(input_path, tmp_path / "out", midi_stems={"bass"}, create_zip=True)

    assert zip_calls == 1
    assert result.zip_path is not None
    with ZipFile(result.zip_path) as archive:
        manifest = archive.read("pitchstems.project.json").decode("utf-8")
    assert '"source_audio": "audio/source.mp3"' in manifest
    assert '"zip_path": "source_pitchstems.zip"' in manifest


def test_project_dir_avoids_same_second_name_collision(tmp_path: Path) -> None:
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"audio")
    first = _project_dir(tmp_path, audio_path)
    first.mkdir()

    second = _project_dir(tmp_path, audio_path)

    assert second != first
    assert second.name.endswith("-2.pitchstems")


def _write_midi(path: Path, note: int) -> None:
    midi = MidiFile()
    track = MidiTrack()
    track.append(Message("note_on", note=note, velocity=64, time=0))
    track.append(Message("note_off", note=note, velocity=0, time=120))
    midi.tracks.append(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)
