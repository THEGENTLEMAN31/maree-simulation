"""Génère les assets du décor de Port-Aubel (Godot et web), de façon déterministe.

    uv run python scripts/generate_assets.py

Aucun fichier source externe : tout est calculé ici, à graine fixe. Palette
volontairement neutre : le rouge est réservé au danger, le bleu, l'ambre et le
mauve aux sorties. Les personnes ne sont pas des assets : à 6-9 px, seules leurs
formes restent lisibles, et elles portent l'information.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "godot/project/assets", ROOT / "web/assets"]
RNG = np.random.default_rng(1848)


def save(image: Image.Image, name: str) -> None:
    for target in TARGETS:
        target.mkdir(parents=True, exist_ok=True)
        image.save(target / name, optimize=True)


def value_noise(size: int, cells: int, seed: int) -> np.ndarray:
    """Bruit périodique : il se raccorde sur les bords, donc le pavage aussi."""
    grid = np.random.default_rng(seed).random((cells, cells))
    t = np.arange(size) * cells / size
    i = t.astype(int)
    f = t - i
    f = f * f * (3 - 2 * f)
    a, b = i % cells, (i + 1) % cells
    rows = grid[a][:, a] * (1 - f)[None, :] + grid[a][:, b] * f[None, :]
    rows2 = grid[b][:, a] * (1 - f)[None, :] + grid[b][:, b] * f[None, :]
    return rows * (1 - f)[:, None] + rows2 * f[:, None]


def fractal(size: int, seed: int, base: int = 8) -> np.ndarray:
    out = np.zeros((size, size))
    for octave in range(4):
        out += value_noise(size, base * 2**octave, seed + octave) / 2**octave
    return out / out.max()


def paving(size: int = 1024, cells: int = 26) -> Image.Image:
    """Pavés de pierre, périodiques (Worley F1/F2), éclairés du nord-ouest."""
    jitter = RNG.random((cells, cells, 2))
    tone = RNG.random((cells, cells))
    ys, xs = np.mgrid[0:size, 0:size] * (cells / size)
    cx, cy = xs.astype(int), ys.astype(int)
    f1 = np.full((size, size), 9.0)
    f2 = np.full((size, size), 9.0)
    owner = np.zeros((size, size))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gx, gy = (cx + dx) % cells, (cy + dy) % cells
            px = cx + dx + 0.15 + 0.7 * jitter[gy, gx, 0]
            py = cy + dy + 0.15 + 0.7 * jitter[gy, gx, 1]
            d = np.hypot(px - xs, py - ys)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            owner = np.where(closer, tone[gy, gx], owner)
            f1 = np.where(closer, d, f1)
    edge = np.clip((f2 - f1) / 0.16, 0, 1)
    dome = np.sqrt(edge)
    grain = fractal(size, 7, 32)
    height = dome + grain * 0.22
    light = (np.roll(height, 2, 1) - np.roll(height, -2, 1)) + (np.roll(height, 2, 0) - np.roll(height, -2, 0))
    value = 44 + owner * 15 + (grain - 0.5) * 16 + light * 34
    value = value * (0.2 + 0.8 * dome)
    rgb = np.stack([value * 0.97, value, value * 1.12], axis=-1)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def canvas(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def texture(image: Image.Image, seed: int, strength: float) -> Image.Image:
    """Grain de matière, appliqué sur les zones opaques."""
    width, height = image.size
    size = max(width, height)
    noise = fractal(size, seed, 16)[:height, :width] - 0.5
    data = np.asarray(image).astype(float)
    data[..., :3] += noise[..., None] * strength
    return Image.fromarray(np.clip(data, 0, 255).astype(np.uint8), "RGBA")


def tour(size: int = 256) -> Image.Image:
    """Toit d'ardoise à quatre pans, vu du dessus."""
    image, draw = canvas(size, size)
    c = size / 2
    pans = [
        ([(0, 0), (size, 0), (c, c)], 92),
        ([(0, 0), (0, size), (c, c)], 78),
        ([(size, 0), (size, size), (c, c)], 56),
        ([(0, size), (size, size), (c, c)], 46),
    ]
    for points, shade in pans:
        draw.polygon(points, fill=(shade, shade + 3, shade + 12, 255))
    step = size // 16
    for r in range(step, int(c), step):
        draw.rectangle((c - r, c - r, c + r, c + r), outline=(20, 21, 28, 150), width=2)
    for x, y in [(0, 0), (size, 0), (0, size), (size, size)]:
        draw.line((x, y, c, c), fill=(150, 154, 170, 255), width=5)
    draw.rectangle((0, 0, size - 1, size - 1), outline=(28, 29, 36, 255), width=7)
    draw.ellipse((c - 15, c - 15, c + 15, c + 15), fill=(170, 174, 188, 255), outline=(30, 31, 38, 255), width=4)
    return texture(image, 21, 26)


def scene(width: int = 512, height: int = 320) -> Image.Image:
    """Plancher de scène : lames de bois, rampe de projecteurs au sud."""
    image, draw = canvas(width, height)
    plank = 26
    for i, y in enumerate(range(0, height, plank)):
        base = 66 + int(RNG.integers(-9, 10))
        draw.rectangle((0, y, width, y + plank), fill=(base + 18, base + 2, base - 16, 255))
        draw.line((0, y, width, y), fill=(24, 18, 14, 255), width=3)
        joint = int(RNG.integers(40, width - 40))
        draw.line((joint, y, joint, y + plank), fill=(24, 18, 14, 255), width=3)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(26, 22, 20, 255), width=10)
    image = texture(image, 33, 34)
    draw = ImageDraw.Draw(image)
    for x in range(36, width - 20, 62):
        draw.ellipse((x - 9, height - 34, x + 9, height - 16), fill=(226, 220, 200, 255), outline=(30, 28, 26, 255), width=3)
    return image


def stand(width: int = 240, height: int = 160) -> Image.Image:
    """Bâche de stand à rayures, avec son festonnage."""
    image, draw = canvas(width, height)
    band = width // 8
    for i in range(8):
        colour = (176, 178, 190, 255) if i % 2 else (88, 92, 110, 255)
        draw.rectangle((i * band, 0, (i + 1) * band, height), fill=colour)
    # Faîtage au milieu : chaque pan s'assombrit en descendant vers le bord.
    fold = 1 - 0.34 * np.abs(np.arange(height) / height - 0.5) * 2
    data = np.asarray(image).astype(float)
    data[..., :3] *= fold[:, None, None]
    image = Image.fromarray(data.astype(np.uint8), "RGBA")
    draw = ImageDraw.Draw(image)
    draw.line((0, height / 2, width, height / 2), fill=(30, 30, 38, 255), width=3)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(24, 24, 30, 255), width=5)
    return texture(image, 45, 18)


def fontaine(size: int = 320) -> Image.Image:
    """Bassin de pierre octogonal, eau sombre, vasque centrale."""
    image, draw = canvas(size, size)
    c = size / 2

    def octagon(radius: float) -> list[tuple[float, float]]:
        angles = np.deg2rad(np.arange(8) * 45 + 22.5)
        return [(c + radius * np.cos(a), c + radius * np.sin(a)) for a in angles]

    draw.polygon(octagon(c * 1.05), fill=(116, 118, 130, 255))
    draw.polygon(octagon(c * 0.8), fill=(44, 46, 54, 255))
    water = np.zeros((size, size, 4), np.uint8)
    ys, xs = np.mgrid[0:size, 0:size]
    r = np.hypot(xs - c, ys - c) / c
    ripple = 0.5 + 0.5 * np.sin(r * 44 + fractal(size, 51, 8) * 7)
    water[..., 0] = 22 + ripple * 22
    water[..., 1] = 58 + ripple * 44
    water[..., 2] = 76 + ripple * 54
    water[..., 3] = 255
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(octagon(c * 0.74), fill=255)
    image.paste(Image.fromarray(water, "RGBA"), (0, 0), mask.filter(ImageFilter.GaussianBlur(1)))
    draw = ImageDraw.Draw(image)
    draw.ellipse((c - 34, c - 34, c + 34, c + 34), fill=(128, 130, 142, 255), outline=(40, 42, 50, 255), width=5)
    draw.ellipse((c - 15, c - 15, c + 15, c + 15), fill=(188, 214, 226, 255))
    return texture(image, 57, 16)


def main() -> None:
    save(paving(), "paving.png")
    save(tour(), "tour.png")
    save(scene(), "scene.png")
    save(stand(), "stand.png")
    save(fontaine(), "fontaine.png")


if __name__ == "__main__":
    main()
