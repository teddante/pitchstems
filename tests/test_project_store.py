from pathlib import Path

from pitchstems.pipeline import PipelineResult
from pitchstems.project_store import (
    PROJECT_FILENAME,
    load_pipeline_result,
    load_project_manifest,
    save_project_manifest,
)
from pitchstems.separation import SeparationOptions, StemResult
from pitchstems.transcription import MidiOptions, MidiResult


def test_save_and_load_project_manifest_round_trip(tmp_path: Path) -> None:
    project_dir = tmp_path / "song.pitchstems"
    normalized = project_dir / "work" / "song.wav"
    stem = project_dir / "stems" / "song_bass.wav"
    midi = project_dir / "midi" / "bass" / "song_bass.mid"
    combined = project_dir / "export" / "song_combined.mid"
    zip_path = project_dir / "song_pitchstems.zip"
    for path in [normalized, stem, midi, combined, zip_path]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder", encoding="utf-8")

    result = PipelineResult(
        project_dir=project_dir,
        normalized_audio=normalized,
        stems=[StemResult("bass", stem)],
        midi_files=[MidiResult("bass", midi)],
        combined_midi=combined,
        zip_path=zip_path,
        source_audio=tmp_path / "source.mp3",
    )

    manifest_path = save_project_manifest(
        result,
        separation_options=SeparationOptions(device="cuda:0"),
        midi_options=MidiOptions(onset_threshold=0.42),
        midi_stems={"bass"},
        generate_midi=True,
        midi_policy="all",
        create_zip=True,
        track_visibility={"bass": True},
        track_audio_enabled={"bass": True},
        track_audio_volume={"bass": 80},
        track_midi_enabled={"bass": False},
        track_midi_volume={"bass": 70},
        playhead_seconds=12.5,
        chord_overrides=[
            {"start": 10.0, "end": 12.0, "label": "Gmaj9", "confidence": 0.93}
        ],
    )
    loaded = load_pipeline_result(manifest_path)
    manifest = load_project_manifest(manifest_path)

    assert manifest_path == project_dir / PROJECT_FILENAME
    assert loaded.project_dir == project_dir
    assert loaded.normalized_audio == normalized
    assert loaded.stems == [StemResult("bass", stem)]
    assert loaded.midi_files == [MidiResult("bass", midi)]
    assert loaded.combined_midi == combined
    assert loaded.zip_path == zip_path
    assert loaded.source_audio == tmp_path / "source.mp3"
    assert manifest["editor"]["chord_overrides"] == [
        {"start": 10.0, "end": 12.0, "label": "Gmaj9", "confidence": 0.93}
    ]
