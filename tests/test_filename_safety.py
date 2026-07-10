from pitchstems.filename_safety import is_windows_reserved_name, safe_file_stem, safe_stem_key


def test_safe_file_stem_uses_fallback_for_empty_reserved_and_unsafe_names() -> None:
    assert safe_file_stem("...", fallback="audio") == "audio"
    assert safe_file_stem("CON", fallback="audio") == "audio_CON"
    assert safe_file_stem("nul", fallback="preview") == "preview_nul"
    assert safe_file_stem("song?title", fallback="audio") == "song_title"


def test_safe_file_stem_trims_long_names_without_trailing_separators() -> None:
    assert safe_file_stem("abc---", fallback="audio", max_length=5) == "abc"
    assert safe_file_stem("abcdef", fallback="audio", max_length=4) == "abcd"


def test_is_windows_reserved_name_is_case_insensitive() -> None:
    assert is_windows_reserved_name("COM1")
    assert is_windows_reserved_name("nul")
    assert not is_windows_reserved_name("song")


def test_safe_stem_key_is_bounded_and_windows_safe() -> None:
    assert safe_stem_key("../../Lead Vocal") == "lead-vocal"
    assert safe_stem_key("CON") == "stem-con"
    assert len(safe_stem_key("a" * 200)) == 80
