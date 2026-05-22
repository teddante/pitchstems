import sys

from pitchstems.separation import _redirect_output


def test_redirect_output_captures_stderr_when_console_stream_is_missing(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(sys, "stderr", None)

    with _redirect_output(messages.append):
        print("progress update", file=sys.stderr)

    assert messages == ["progress update"]
