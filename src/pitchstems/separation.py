from __future__ import annotations

import argparse
import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pitchstems.model_catalog import ModelChoice, model_choice


@dataclass(frozen=True)
class SeparationProfile:
    key: str
    label: str
    best_for: str
    expected_stems: list[str]
    models: list[str]


DEFAULT_PROFILE_KEY = "song-6-stem"

LEGACY_PROFILE_ALIASES = {
    "best": "song-6-stem",
    "balanced": "song-6-stem",
    "song-4-stem": "song-6-stem",
    "song-6-stem": "song-6-stem",
}

PROFILE_MODEL_ALIASES = {
    DEFAULT_PROFILE_KEY: "bs_roformer_sw",
}


@dataclass(frozen=True)
class SeparationOptions:
    model_key: str = "bs_roformer_sw"
    selected_stem: str | None = None
    device: str | None = None
    device_ids: tuple[int, ...] | None = None

    @property
    def choice(self) -> ModelChoice:
        return model_choice(self.model_key)


@dataclass(frozen=True)
class StemResult:
    name: str
    path: Path
    stem_id: str | None = None

    @property
    def safe_key(self) -> str:
        return self.stem_id or safe_stem_key(self.name)


def safe_stem_key(value: str) -> str:
    cleaned = []
    previous_dash = False
    for character in value.strip().lower():
        if character.isalnum():
            cleaned.append(character)
            previous_dash = False
        elif not previous_dash:
            cleaned.append("-")
            previous_dash = True
    key = "".join(cleaned).strip("-")
    return key or "stem"


class SeparationDependencyError(RuntimeError):
    """Raised when the optional native separation backend is not installed."""


def download_model(model_key: str, log: Callable[[str], None] | None = None) -> Path:
    """Download a curated native BS-RoFormer model without processing audio."""
    try:
        from bs_roformer import MODEL_REGISTRY
        from bs_roformer.download import download_model_assets
    except ImportError as exc:
        raise SeparationDependencyError(
            "bs-roformer-infer is not installed. Install with `pip install -e .[win-gpu,gui]`."
        ) from exc

    choice = model_choice(model_key)
    model_dir = _model_cache_dir()
    model_dir.mkdir(parents=True, exist_ok=True)
    native_model = _registry_model(MODEL_REGISTRY, choice)
    if log:
        log("Native backend: bs-roformer-infer")
        log(f"Model registry id: {choice.native_model_id}")
        log(f"Model cache: {model_dir}")
    ok = download_model_assets([native_model], model_dir)
    if not ok:
        raise RuntimeError(f"Failed to download {choice.label}")
    return model_dir


def separate_stems(
    audio_path: Path,
    output_dir: Path,
    profile: str = "song-6-stem",
    options: SeparationOptions | None = None,
    log: Callable[[str], None] | None = None,
) -> list[StemResult]:
    """Separate an audio file into stems using native bs-roformer-infer."""
    try:
        from bs_roformer import MODEL_REGISTRY
        from bs_roformer.inference import proc_folder
    except ImportError as exc:
        raise SeparationDependencyError(
            "bs-roformer-infer is not installed. Install with `pip install -e .[win-gpu,gui]`."
        ) from exc

    if options is None:
        options = SeparationOptions(model_key=model_key_for_profile(profile))

    choice = options.choice
    model_dir = download_model(choice.key, log=log)
    native_model = _registry_model(MODEL_REGISTRY, choice)
    native_dir = model_dir / native_model.slug
    model_path = native_dir / native_model.checkpoint
    config_path = native_dir / native_model.config
    if not model_path.exists() or not config_path.exists():
        raise FileNotFoundError(f"Native BS-RoFormer assets are missing from {native_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in output_dir.glob("*.wav")}

    if log:
        log(f"Separation goal: {choice.best_for}")
        log("Native backend: bs-roformer-infer")
        log(f"Model: {choice.label}")
        log(f"Model config: {config_path}")
        log(f"Model weights: {model_path}")
        log(f"Expected stems: {', '.join(choice.stems)}")
        if options.selected_stem:
            log(f"Single-stem export requested after separation: {options.selected_stem}")
        log(f"Device request: {options.device or 'auto (CUDA if PyTorch can see it, otherwise CPU)'}")
        if options.device_ids:
            log(f"GPU ids: {', '.join(str(device_id) for device_id in options.device_ids)}")
        log(f"Acceleration: {choice.gpu_note}")

    args = argparse.Namespace(
        model_type="bs_roformer",
        config_path=config_path,
        model_path=model_path,
        input_folder=audio_path.parent,
        store_dir=output_dir,
        device=options.device,
        device_ids=list(options.device_ids) if options.device_ids else None,
    )
    with _redirect_output(log):
        proc_folder(args)

    produced = sorted(path for path in output_dir.glob("*.wav") if path.resolve() not in before)
    stems = _dedupe_stems([StemResult(name=_guess_stem_name(path), path=path) for path in produced])
    if not stems:
        raise RuntimeError(
            "BS-RoFormer did not produce any stems. "
            "Check the selected model, device, and native backend logs."
        )
    if options.selected_stem:
        requested = options.selected_stem.lower()
        stems = [stem for stem in stems if stem.name.lower() == requested]
        if not stems:
            raise RuntimeError(f"BS-RoFormer did not produce requested stem: {options.selected_stem}")
    return stems


def get_profile(profile: str) -> SeparationProfile:
    key = LEGACY_PROFILE_ALIASES.get(profile, profile)
    if key not in PROFILE_MODEL_ALIASES:
        key = DEFAULT_PROFILE_KEY
    choice = model_choice(PROFILE_MODEL_ALIASES[key])
    return SeparationProfile(
        key=key,
        label=choice.label,
        best_for=choice.best_for,
        expected_stems=choice.stems,
        models=[choice.native_model_id],
    )


def model_key_for_profile(profile: str) -> str:
    return PROFILE_MODEL_ALIASES.get(get_profile(profile).key, "bs_roformer_sw")


def profile_keys() -> list[str]:
    return list(PROFILE_MODEL_ALIASES)


def _model_cache_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "PitchStems" / "bs-roformer-models"
    return Path.home() / ".cache" / "pitchstems" / "bs-roformer-models"


def _registry_model(registry, choice: ModelChoice):
    native_model = registry.get(choice.native_model_id)
    if native_model is None:
        raise RuntimeError(
            f"Native BS-RoFormer registry id is unavailable: {choice.native_model_id}. "
            "Update bs-roformer-infer or choose a different bundled model."
        )
    return native_model


@contextlib.contextmanager
def _redirect_output(log: Callable[[str], None] | None):
    if log is None:
        yield
        return

    class LogWriter:
        def __init__(self) -> None:
            self.buffer = ""

        def write(self, text: str) -> int:
            self.buffer += text
            while "\n" in self.buffer:
                line, self.buffer = self.buffer.split("\n", 1)
                if line.strip():
                    log(line.rstrip())
            return len(text)

        def flush(self) -> None:
            if self.buffer.strip():
                log(self.buffer.rstrip())
            self.buffer = ""

    writer = LogWriter()
    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
        yield
    writer.flush()


def _guess_stem_name(path: Path) -> str:
    lower = path.stem.lower()
    known = [
        "instrumental",
        "vocals",
        "drums",
        "bass",
        "guitar",
        "piano",
        "other",
        "dry",
        "wet",
        "male",
        "female",
    ]
    for stem in known:
        if lower.endswith(f"_{stem}") or lower == stem or f"_{stem}_" in lower:
            return stem
    return path.stem


def _dedupe_stems(stems: list[StemResult]) -> list[StemResult]:
    by_name: dict[str, StemResult] = {}
    for stem in stems:
        by_name[stem.name] = stem
    return list(by_name.values())
