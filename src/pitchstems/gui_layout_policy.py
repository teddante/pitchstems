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
        return 380 if self.compact else 460

    @property
    def track_panel_min_width(self) -> int:
        return 240 if self.compact else 280

    @property
    def track_panel_width(self) -> int:
        return self.track_panel_min_width


@dataclass(frozen=True)
class PipelineLayoutPolicy:
    pipeline_intro: str = (
        "Drop audio, choose output settings, then run the local BS-RoFormer and Basic Pitch pipeline."
    )
