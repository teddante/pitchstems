from pitchstems.gui_options import default_midi_checked, device_label, optional_frequency


def test_optional_frequency_treats_zero_as_unbounded() -> None:
    assert optional_frequency(0.0) is None
    assert optional_frequency(-10.0) is None
    assert optional_frequency(82.4) == 82.4


def test_default_midi_checked_excludes_unpitched_or_mix_stems() -> None:
    assert default_midi_checked("bass") is True
    assert default_midi_checked("drums") is False
    assert default_midi_checked("Drum") is False
    assert default_midi_checked("kick") is False


def test_device_label_describes_auto_and_forced_modes() -> None:
    assert device_label("cpu", cuda_available=True) == "PyTorch CPU (forced)"
    assert device_label("cuda:0", cuda_available=True) == "PyTorch CUDA (cuda:0)"
    assert device_label(None, cuda_available=True) == "PyTorch CUDA (auto)"
    assert device_label(None, cuda_available=False) == "PyTorch CPU (auto fallback)"
