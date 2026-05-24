import sys

import pytest

from pitchstems.model_catalog import model_choice
from pitchstems.separation import _redirect_output, _registry_model


def test_redirect_output_captures_stderr_when_console_stream_is_missing(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(sys, "stderr", None)

    with _redirect_output(messages.append):
        print("progress update", file=sys.stderr)

    assert messages == ["progress update"]


def test_registry_model_reports_missing_native_model_id() -> None:
    with pytest.raises(RuntimeError, match="registry id is unavailable"):
        _registry_model({}, model_choice("bs_roformer_sw"))
