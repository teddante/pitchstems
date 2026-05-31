from pitchstems.time_format import format_time


def test_format_time_clamps_negative_values_to_zero() -> None:
    assert format_time(-1.25) == "00:00.000"


def test_format_time_formats_minutes_and_milliseconds() -> None:
    assert format_time(65.4321) == "01:05.432"
    assert format_time(125.0) == "02:05.000"
