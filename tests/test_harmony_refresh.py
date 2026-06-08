from __future__ import annotations

from pitchstems.gui_harmony_flow import HarmonyRefreshGate


def test_harmony_refresh_gate_allows_initial_and_throttles_close_updates() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert not gate.should_refresh(10.1, now_seconds=1.10)
    assert gate.should_refresh(10.2, now_seconds=1.26)


def test_harmony_refresh_gate_forces_selection_changes() -> None:
    gate = HarmonyRefreshGate(min_interval_seconds=0.25)
    assert gate.should_refresh(10.0, now_seconds=1.00)
    assert gate.should_refresh(10.0, now_seconds=1.05, force=True)
