import math

import pytest

from pitchstems.audio_clip import AudioClipRange, clamp_clip_range, clip_range_from_manifest


def test_clip_range_clamps_and_treats_full_file_as_no_clip() -> None:
    assert clamp_clip_range(-2.0, 12.0, 10.0) is None
    assert clamp_clip_range(3.0, 1.0, 10.0) == AudioClipRange(1.0, 3.0)
    assert clamp_clip_range(1.0, 1.01, 10.0) is None


def test_clip_range_round_trips_manifest_values() -> None:
    clip = AudioClipRange(2.5, 8.0)

    loaded = clip_range_from_manifest(clip.to_manifest())

    assert loaded == clip
    assert loaded.duration_seconds == 5.5


@pytest.mark.parametrize("start,end", [(math.nan, 1.0), (0.0, math.inf)])
def test_clip_range_rejects_non_finite_times(start: float, end: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        AudioClipRange(start, end)


def test_clamp_clip_range_rejects_non_finite_inputs() -> None:
    assert clamp_clip_range(math.nan, 1.0, 10.0) is None
