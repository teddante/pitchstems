from __future__ import annotations


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def is_windows_reserved_name(name: str) -> bool:
    return name.upper() in WINDOWS_RESERVED_NAMES


def safe_file_stem(value: str, fallback: str, max_length: int = 80) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    safe = safe.strip("._-")[:max_length].rstrip("._-")
    if not safe:
        safe = fallback
    if is_windows_reserved_name(safe):
        safe = f"{fallback}_{safe}"
    return safe
