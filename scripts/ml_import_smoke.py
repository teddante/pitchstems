from __future__ import annotations

import importlib
import importlib.metadata
import logging


RUNTIME_MODULES = {
    "basic-pitch": "basic_pitch",
    "bs-roformer-infer": "bs_roformer",
    "torch": "torch",
}


def main() -> int:
    for distribution, module_name in RUNTIME_MODULES.items():
        logging.disable(logging.WARNING)
        module = importlib.import_module(module_name)
        logging.disable(logging.NOTSET)
        version = importlib.metadata.version(distribution)
        print(f"OK {distribution} {version}: imported {module.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
