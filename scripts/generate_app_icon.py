from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    asset_dir = root / "src" / "pitchstems" / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    image = _draw_icon(1024)
    image.save(asset_dir / "pitchstems.png")
    image.save(
        asset_dir / "pitchstems.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def _draw_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 12
    rect = (margin, margin, size - margin, size - margin)
    radius = size // 5
    draw.rounded_rectangle(rect, radius=radius, fill="#0f172a")
    inset = size // 7
    draw.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=size // 6,
        outline="#38bdf8",
        width=size // 28,
    )

    wave = []
    left = size * 0.20
    right = size * 0.80
    center = size * 0.50
    amplitude = size * 0.11
    steps = 84
    for index in range(steps + 1):
        x = left + ((right - left) * index / steps)
        phase = index / steps
        y = center + amplitude * _sine_like(phase)
        wave.append((x, y))
    draw.line(wave, fill="#f8fafc", width=size // 30, joint="curve")

    stem_x = size * 0.62
    stem_top = size * 0.25
    stem_bottom = size * 0.70
    draw.line((stem_x, stem_top, stem_x, stem_bottom), fill="#f97316", width=size // 26)
    draw.ellipse(
        (
            stem_x - size * 0.18,
            stem_bottom - size * 0.03,
            stem_x + size * 0.03,
            stem_bottom + size * 0.18,
        ),
        fill="#f97316",
    )
    draw.polygon(
        [
            (stem_x, stem_top),
            (stem_x + size * 0.20, stem_top + size * 0.06),
            (stem_x + size * 0.20, stem_top + size * 0.16),
            (stem_x, stem_top + size * 0.10),
        ],
        fill="#fbbf24",
    )
    return image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120))


def _sine_like(phase: float) -> float:
    if phase < 0.25:
        return -phase * 4
    if phase < 0.5:
        return -1 + ((phase - 0.25) * 4)
    if phase < 0.75:
        return (phase - 0.5) * 4
    return 1 - ((phase - 0.75) * 4)


if __name__ == "__main__":
    main()
