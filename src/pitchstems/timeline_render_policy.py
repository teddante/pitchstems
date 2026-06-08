from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimelineRenderPolicy:
    pixels_per_second: float
    visible_note_count: int

    @property
    def draw_note_labels(self) -> bool:
        return self.pixels_per_second >= 150 and self.visible_note_count <= 900

    @property
    def dense_render(self) -> bool:
        return self.pixels_per_second < 55 or self.visible_note_count > 2400

    @property
    def enable_tooltips(self) -> bool:
        return self.visible_note_count <= 1400 and not self.dense_render
