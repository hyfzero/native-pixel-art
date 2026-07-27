from __future__ import annotations

import numpy as np
from PIL import Image


def foreground_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    rgba = np.asarray(image.convert("RGBA"))
    alpha = rgba[..., 3]
    if np.any(alpha < 250):
        mask = alpha > 8
    else:
        corners = np.stack([rgba[0, 0, :3], rgba[0, -1, :3], rgba[-1, 0, :3], rgba[-1, -1, :3]])
        background = np.median(corners.astype(np.float32), axis=0)
        distance = np.sqrt(np.sum((rgba[..., :3].astype(np.float32) - background) ** 2, axis=-1))
        mask = distance > 24
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def crop_subject(image: Image.Image) -> tuple[Image.Image, dict]:
    rgba = image.convert("RGBA")
    bbox = foreground_bbox(rgba)
    if bbox is None:
        return rgba.copy(), {"bbox": [0, 0, rgba.width, rgba.height], "method": "full-image"}
    return rgba.crop(bbox), {"bbox": list(bbox), "method": "alpha-or-corner-background"}


def place_subject(
    subject: Image.Image,
    canvas_size: tuple[int, int],
    subject_scale: float,
    padding: int,
    alignment: str,
    background: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[Image.Image, dict]:
    width, height = canvas_size
    available_w = max(1, width - padding * 2)
    available_h = max(1, height - padding * 2)
    ratio = min(available_w / subject.width, available_h / subject.height) * subject_scale
    out_w = max(1, min(available_w, int(round(subject.width * ratio))))
    out_h = max(1, min(available_h, int(round(subject.height * ratio))))
    resized = subject.resize((out_w, out_h), Image.Resampling.BOX)
    x = (width - out_w) // 2
    y = (height - out_h) // 2
    if alignment == "top":
        y = padding
    elif alignment == "bottom":
        y = height - padding - out_h
    elif alignment == "left":
        x = padding
    elif alignment == "right":
        x = width - padding - out_w
    canvas = Image.new("RGBA", canvas_size, background)
    canvas.alpha_composite(resized, (x, y))
    return canvas, {"placed_bbox": [x, y, x + out_w, y + out_h], "scale": ratio}
