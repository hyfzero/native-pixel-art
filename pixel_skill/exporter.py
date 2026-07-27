from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .downsample import nearest_preview
from .palette import rgb_to_hex


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def palette_strip(palette: list[tuple[int, int, int]], swatch: int = 16) -> Image.Image:
    image = Image.new("RGB", (max(1, len(palette)) * swatch, swatch), "white")
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(palette):
        draw.rectangle((index * swatch, 0, (index + 1) * swatch - 1, swatch - 1), fill=color)
    return image


def write_json(path: str | Path, data: dict | list) -> None:
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_images(
    image: Image.Image, palette: list[tuple[int, int, int]], output_dir: Path, preview_scale: int
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "final": output_dir / "final.png",
        "preview": output_dir / f"preview_{preview_scale}x.png",
        "palette": output_dir / "palette.png",
    }
    image.save(paths["final"], format="PNG", optimize=False)
    nearest_preview(image, preview_scale).save(paths["preview"], format="PNG", optimize=False)
    palette_strip(palette).save(paths["palette"], format="PNG", optimize=False)
    return paths


def describe_palette(palette: list[tuple[int, int, int]]) -> list[str]:
    return [rgb_to_hex(color) for color in palette]
