from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path

from pitchstems import model_assets
from pitchstems.model_catalog import DEFAULT_MODEL_KEY


def test_model_asset_status_reports_missing_files(tmp_path: Path) -> None:
    statuses = model_assets.model_asset_statuses(DEFAULT_MODEL_KEY, cache_root=tmp_path)

    assert {status.filename for status in statuses} == {
        "BS-Rofo-SW-Fixed.ckpt",
        "BS-Rofo-SW-Fixed.yaml",
    }
    assert all(not status.ok and status.detail == "missing" for status in statuses)


def test_ensure_model_assets_skips_present_cache(monkeypatch, tmp_path: Path) -> None:
    asset = model_assets.ModelAsset(
        filename="tiny.bin",
        size=4,
        sha256="3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7",
        sources=(),
    )
    monkeypatch.setitem(model_assets.MODEL_ASSETS, DEFAULT_MODEL_KEY, (asset,))
    directory = model_assets.model_asset_dir(DEFAULT_MODEL_KEY, cache_root=tmp_path)
    directory.mkdir(parents=True)
    (directory / "tiny.bin").write_bytes(b"data")

    messages: list[str] = []
    statuses = model_assets.ensure_model_assets(DEFAULT_MODEL_KEY, cache_root=tmp_path, log=messages.append)

    assert statuses[0].ok is True
    assert statuses[0].detail == "present"
    assert messages == []


def test_ensure_model_assets_repairs_from_fallback_source(monkeypatch, tmp_path: Path) -> None:
    asset = model_assets.ModelAsset(
        filename="tiny.bin",
        size=4,
        sha256="3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7",
        sources=(
            model_assets.HuggingFaceAssetSource("missing/repo", "tiny.bin", "missing"),
            model_assets.HuggingFaceAssetSource("good/repo", "tiny.bin", "good"),
        ),
    )
    monkeypatch.setitem(model_assets.MODEL_ASSETS, DEFAULT_MODEL_KEY, (asset,))
    directory = model_assets.model_asset_dir(DEFAULT_MODEL_KEY, cache_root=tmp_path)
    directory.mkdir(parents=True)
    (directory / "tiny.bin").write_bytes(b"oops")

    def fake_hf_download(source: model_assets.HuggingFaceAssetSource) -> Path:
        if source.repo_id == "missing/repo":
            raise RuntimeError("not found")
        path = tmp_path / source.path
        path.write_bytes(b"data")
        return path

    monkeypatch.setattr(model_assets, "_hf_download", fake_hf_download)

    statuses = model_assets.ensure_model_assets(
        DEFAULT_MODEL_KEY,
        cache_root=tmp_path,
        verify_hash=True,
    )

    assert statuses[0].detail == "verified"
    assert (model_assets.model_asset_dir(DEFAULT_MODEL_KEY, cache_root=tmp_path) / "tiny.bin").read_bytes() == b"data"


def test_hf_download_uses_the_persistent_huggingface_cache(monkeypatch, tmp_path: Path) -> None:
    downloaded = tmp_path / "cached.bin"
    downloaded.write_bytes(b"data")
    captured: dict[str, str] = {}

    def fake_hf_hub_download(*, repo_id: str, filename: str) -> str:
        captured.update(repo_id=repo_id, filename=filename)
        return str(downloaded)

    fake_huggingface_hub = ModuleType("huggingface_hub")
    fake_huggingface_hub.hf_hub_download = fake_hf_hub_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_huggingface_hub)
    source = model_assets.HuggingFaceAssetSource("publisher/model", "model.bin", "publisher")

    assert model_assets._hf_download(source) == downloaded
    assert captured == {"repo_id": "publisher/model", "filename": "model.bin"}
