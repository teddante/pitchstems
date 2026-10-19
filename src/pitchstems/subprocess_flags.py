from __future__ import annotations

import subprocess
import sys

# The GUI runs without a console (pitchstems-gui.exe), so every console tool it
# starts (FFmpeg, FFprobe, taskkill) would otherwise flash its own window.
NO_CONSOLE_WINDOW: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
