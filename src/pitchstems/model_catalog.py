from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL_KEY = "bs_roformer_sw"


@dataclass(frozen=True)
class ModelChoice:
    key: str
    label: str
    stems: list[str]
    summary: str
    best_for: str
    quality_note: str
    speed_note: str
    gpu_note: str
    native_model_id: str
    source: str = "bs-roformer-infer"
    recommended: bool = False
    score_summary: str = "No directly comparable public SDR score is bundled for this exact method."
    filename: str | None = None
    config_filename: str | None = None

    @property
    def display_label(self) -> str:
        suffix = " - recommended" if self.recommended else ""
        return f"{self.label}{suffix}"


MODEL_CHOICES: dict[str, ModelChoice] = {
    DEFAULT_MODEL_KEY: ModelChoice(
        key=DEFAULT_MODEL_KEY,
        label="BS-RoFormer SW six-stem",
        stems=["vocals", "drums", "bass", "guitar", "piano", "other", "instrumental"],
        summary="Native BS-RoFormer-SW inference for six-stem song separation.",
        best_for="The main PitchStems path: split a full song into MIDI-relevant parts.",
        quality_note="Recommended default in bs-roformer-infer. It uses the model config shipped by the model package.",
        speed_note="Slow: one large six-stem RoFormer model.",
        gpu_note="Uses PyTorch CUDA when available.",
        native_model_id="roformer-model-bs-roformer-sw-by-jarredou",
        recommended=True,
        score_summary="MVSep table: vocals 11.30, backing 17.50, bass 14.62, drums 14.11, guitar 9.05, piano 7.83, other 8.71 SDR.",
        filename="BS-Rofo-SW-Fixed.ckpt",
        config_filename="BS-Rofo-SW-Fixed.yaml",
    ),
}


def model_choice(key: str) -> ModelChoice:
    return MODEL_CHOICES.get(key, MODEL_CHOICES[DEFAULT_MODEL_KEY])
