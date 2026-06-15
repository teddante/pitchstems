from __future__ import annotations

from dataclasses import dataclass


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
    "bs_roformer_sw": ModelChoice(
        key="bs_roformer_sw",
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
    "bs_roformer_vocals_resurrection": ModelChoice(
        key="bs_roformer_vocals_resurrection",
        label="BS-RoFormer vocals resurrection",
        stems=["vocals", "instrumental"],
        summary="Native BS-RoFormer vocal extraction focused on strong vocal quality.",
        best_for="When vocal clarity matters more than six separate instrument stems.",
        quality_note="Single vocal-specialist BS-RoFormer checkpoint from the native registry.",
        speed_note="Medium to slow: one RoFormer vocal model.",
        gpu_note="Uses PyTorch CUDA when available.",
        native_model_id="roformer-model-bs-roformer-vocals-resurrection-by-unwa",
        score_summary="Published preset evidence reports Resurrection vocal SDR around 11.34.",
        filename="bs_roformer_vocals_resurrection_unwa.ckpt",
        config_filename="config_bs_roformer_vocals_resurrection_unwa.yaml",
    ),
    "bs_roformer_vocals_revive_v3e": ModelChoice(
        key="bs_roformer_vocals_revive_v3e",
        label="BS-RoFormer vocals revive v3e",
        stems=["vocals", "instrumental"],
        summary="Native BS-RoFormer vocal model aimed at fuller vocal capture.",
        best_for="Vocals where harmonies or quiet phrases are being lost.",
        quality_note="Single vocal-specialist BS-RoFormer checkpoint from the native registry.",
        speed_note="Medium to slow: one RoFormer vocal model.",
        gpu_note="Uses PyTorch CUDA when available.",
        native_model_id="roformer-model-bs-roformer-vocals-revive-v3e-by-unwa",
        score_summary="No directly comparable public SDR is bundled for this exact checkpoint.",
        filename="bs_roformer_vocals_revive_v3e_unwa.ckpt",
        config_filename="config_bs_roformer_vocals_revive_unwa.yaml",
    ),
    "bs_roformer_instrumental_resurrection": ModelChoice(
        key="bs_roformer_instrumental_resurrection",
        label="BS-RoFormer instrumental resurrection",
        stems=["instrumental", "vocals"],
        summary="Native BS-RoFormer backing-track extraction.",
        best_for="When you mainly want the instrumental/backing track.",
        quality_note="Single instrumental-specialist BS-RoFormer checkpoint from the native registry.",
        speed_note="Medium to slow: one RoFormer instrumental model.",
        gpu_note="Uses PyTorch CUDA when available.",
        native_model_id="roformer-model-bs-roformer-instrumental-resurrection-by-unwa",
        score_summary="No directly comparable public SDR is bundled for this exact checkpoint.",
        filename="bs_roformer_instrumental_resurrection_unwa.ckpt",
        config_filename="config_bs_roformer_instrumental_resurrection_unwa.yaml",
    ),
    "bs_roformer_dereverb": ModelChoice(
        key="bs_roformer_dereverb",
        label="BS-RoFormer de-reverb",
        stems=["dry", "wet", "instrumental"],
        summary="Native BS-RoFormer repair model for reducing reverb.",
        best_for="Drying a wet vocal or stem before MIDI conversion.",
        quality_note="Specialized repair checkpoint; its score is not comparable to music-stem SDR.",
        speed_note="Medium to slow: one RoFormer repair model.",
        gpu_note="Uses PyTorch CUDA when available.",
        native_model_id="roformer-model-bs-roformer-de-reverb",
        score_summary="Specialized de-reverb model; not comparable to music-stem SDR.",
        filename="deverb_bs_roformer_8_384dim_10depth.ckpt",
        config_filename="deverb_bs_roformer_8_384dim_10depth_config.yaml",
    ),
}


def model_choice(key: str) -> ModelChoice:
    return MODEL_CHOICES.get(key, MODEL_CHOICES["bs_roformer_sw"])


def all_model_keys() -> list[str]:
    return list(MODEL_CHOICES)
