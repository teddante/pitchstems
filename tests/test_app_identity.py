from pitchstems.app_identity import APP_NAME, app_icon_path


def test_app_identity_exposes_packaged_icon() -> None:
    icon = app_icon_path()

    assert APP_NAME == "PitchStems"
    assert icon is not None
    assert icon.name == "pitchstems.ico"
    assert icon.exists()
