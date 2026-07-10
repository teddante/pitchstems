from __future__ import annotations


def main() -> int:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print("PySide6 is required for the PitchStems GUI. Install with `pip install -e .[gui]`.")
        return 1

    from pitchstems.app import main as run_app

    return run_app()
