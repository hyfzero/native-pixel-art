from __future__ import annotations

from PIL import Image, ImageFilter


def downsample(image: Image.Image, size: tuple[int, int], method: str = "area") -> Image.Image:
    rgba = image.convert("RGBA")
    if method == "edge_aware":
        rgba = rgba.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=3))
    return rgba.resize(size, Image.Resampling.BOX)


def nearest_preview(image: Image.Image, scale: int) -> Image.Image:
    if scale < 1 or int(scale) != scale:
        raise ValueError("preview scale must be a positive integer")
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
