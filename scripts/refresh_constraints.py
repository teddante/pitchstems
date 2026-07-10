from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


PROFILES = {
    "dev": ("dev", "gui"),
    "cpu": ("cpu", "dev", "gui"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate a Windows PitchStems constraints file.")
    parser.add_argument("profile", choices=PROFILES)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows constraints must be regenerated on Windows.")

    root = Path(__file__).resolve().parents[1]
    output = root / "constraints" / f"windows-{args.profile}.txt"
    with tempfile.TemporaryDirectory(prefix="pitchstems-constraints-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "Scripts" / "python.exe"
        extras = ",".join(PROFILES[args.profile])
        subprocess.run([python, "-m", "pip", "install", "-U", "pip", "setuptools"], check=True)
        subprocess.run([python, "-m", "pip", "install", f"{root}[{extras}]"], check=True)
        freeze = subprocess.run(
            [python, "-m", "pip", "freeze", "--exclude-editable"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    header = f"# Generated on Windows with: py -3.10 scripts/refresh_constraints.py {args.profile}"
    output.write_text("\n".join([header, *sorted(freeze, key=str.casefold), ""]), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
