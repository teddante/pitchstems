from __future__ import annotations

import pytest

from pitchstems.gui_helpers import blocked_signals


class _SignalWidget:
    def __init__(self, blocked: bool = False) -> None:
        self.blocked = blocked
        self.calls: list[tuple[bool, bool]] = []

    def blockSignals(self, blocked: bool) -> bool:
        previous = self.blocked
        self.calls.append((blocked, previous))
        self.blocked = blocked
        return previous


def test_blocked_signals_restores_previous_signal_state() -> None:
    widget = _SignalWidget()

    with blocked_signals(widget):
        assert widget.blocked is True

    assert widget.blocked is False
    assert widget.calls == [(True, False), (False, True)]


def test_blocked_signals_restores_already_blocked_widget_after_exception() -> None:
    widget = _SignalWidget(blocked=True)

    with pytest.raises(RuntimeError):
        with blocked_signals(widget):
            raise RuntimeError("failed update")

    assert widget.blocked is True
    assert widget.calls == [(True, True), (True, True)]
