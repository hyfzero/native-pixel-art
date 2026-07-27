from __future__ import annotations

import numpy as np
from PIL import Image

from .config import PixelArtRequest


def split_source_frames(source: Image.Image, request: PixelArtRequest) -> list[Image.Image]:
    count = request.animation.frame_count
    columns = request.animation.columns
    rows = request.animation.rows
    if source.width % columns or source.height % rows:
        raise ValueError("animation source dimensions are not divisible by the requested grid")
    cell_width = source.width // columns
    cell_height = source.height // rows
    frames = []
    for index in range(count):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        frames.append(source.crop((x, y, x + cell_width, y + cell_height)).convert("RGBA"))
    return frames


def assemble_frames(frames: list[Image.Image], request: PixelArtRequest) -> Image.Image:
    width, height = request.output_size
    frame_width, frame_height = request.frame_size
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        x = (index % request.animation.columns) * frame_width
        y = (index // request.animation.columns) * frame_height
        sheet.alpha_composite(frame, (x, y))
    return sheet


def frame_anchor(frame: Image.Image) -> dict:
    rgba = np.asarray(frame.convert("RGBA"))
    ys, xs = np.where(rgba[..., 3] > 0)
    if len(xs) == 0:
        return {"empty": True, "anchor_x": None, "baseline": None}
    return {
        "empty": False,
        "anchor_x": round(float((xs.min() + xs.max()) / 2), 3),
        "baseline": int(ys.max()),
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
    }


def animation_metrics(frames: list[Image.Image]) -> list[dict]:
    return [{"frame": index, **frame_anchor(frame)} for index, frame in enumerate(frames)]
