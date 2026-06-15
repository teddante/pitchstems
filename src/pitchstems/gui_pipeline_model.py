from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelinePageModel:
    busy: bool
    has_result: bool
    generate_midi: bool

    @property
    def drop_zone_enabled(self) -> bool:
        return not self.busy

    @property
    def run_full_enabled(self) -> bool:
        return not self.busy

    @property
    def run_midi_enabled(self) -> bool:
        return (not self.busy) and self.has_result

    @property
    def export_enabled(self) -> bool:
        return (not self.busy) and self.has_result

    @property
    def cancel_enabled(self) -> bool:
        return self.busy

    @property
    def settings_enabled(self) -> bool:
        return not self.busy

    @property
    def midi_stem_checks_enabled(self) -> bool:
        return (not self.busy) and self.generate_midi
