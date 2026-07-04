from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditorLayoutPolicy:
    window_width: int

    @property
    def compact(self) -> bool:
        return self.window_width < 1040

    @property
    def harmony_panel_min_width(self) -> int:
        return 260 if self.compact else 300

    @property
    def harmony_panel_width(self) -> int:
        return 360 if self.compact else 440

    @property
    def track_panel_min_width(self) -> int:
        return 220 if self.compact else 250

    @property
    def track_panel_width(self) -> int:
        return 250 if self.compact else 280


@dataclass(frozen=True)
class PipelineLayoutPolicy:
    pipeline_intro: str = (
        "Drop audio, choose output settings, then run the local BS-RoFormer and Basic Pitch pipeline."
    )
