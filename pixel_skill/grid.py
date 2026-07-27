from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .config import PixelArtRequest
from .palette import hex_to_rgb, rgb_to_hex


def image_to_grid(image: Image.Image, palette: list[tuple[int, int, int]]) -> list[list[int]]:
    rgba = np.asarray(image.convert("RGBA"))
    lookup = {tuple(color): index for index, color in enumerate(palette)}
    grid: list[list[int]] = []
    for row in rgba:
        values: list[int] = []
        for pixel in row:
            if int(pixel[3]) == 0:
                values.append(-1)
            else:
                color = tuple(int(value) for value in pixel[:3])
                if color not in lookup:
                    raise ValueError(f"image contains color outside canonical palette: {color}")
                values.append(lookup[color])
        grid.append(values)
    return grid


def grid_to_image(grid: list[list[int]], palette: list[tuple[int, int, int]]) -> Image.Image:
    height = len(grid)
    width = len(grid[0]) if height else 0
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for y, row in enumerate(grid):
        if len(row) != width:
            raise ValueError("grid rows have inconsistent widths")
        for x, index in enumerate(row):
            if index < 0:
                continue
            if index >= len(palette):
                raise ValueError(f"grid palette index out of range: {index}")
            rgba[y, x, :3] = palette[index]
            rgba[y, x, 3] = 255
    return Image.fromarray(rgba, "RGBA")


def apply_patches(
    frames: list[list[list[int]]],
    request: PixelArtRequest,
    palette: list[tuple[int, int, int]],
) -> None:
    lookup = {rgb_to_hex(color): index for index, color in enumerate(palette)}
    for patch in request.patches:
        if patch.frame >= len(frames):
            raise ValueError(f"patch frame {patch.frame} is out of range")
        grid = frames[patch.frame]
        height = len(grid)
        width = len(grid[0]) if height else 0
        patch_width = 1 if patch.operation == "set_pixel" else patch.width
        patch_height = 1 if patch.operation == "set_pixel" else patch.height
        if patch.x + patch_width > width or patch.y + patch_height > height:
            raise ValueError("pixel patch exceeds frame bounds")
        if patch.transparent:
            index = -1
        else:
            color = rgb_to_hex(hex_to_rgb(patch.color or ""))
            if color not in lookup:
                raise ValueError(f"patch color {color} is not in the canonical palette")
            index = lookup[color]
        for y in range(patch.y, patch.y + patch_height):
            for x in range(patch.x, patch.x + patch_width):
                grid[y][x] = index


def write_grid(
    path: Path,
    frames: list[list[list[int]]],
    palette: list[tuple[int, int, int]],
    request: PixelArtRequest,
) -> None:
    payload = {
        "schema_version": 1,
        "asset_id": request.asset_id,
        "asset_type": request.asset_type,
        "palette": [rgb_to_hex(color) for color in palette],
        "transparent_index": -1,
        "frame_width": request.frame_size[0],
        "frame_height": request.frame_size[1],
        "frame_count": len(frames),
        "columns": request.animation.columns if request.asset_type == "animation" else 1,
        "rows": request.animation.rows if request.asset_type == "animation" else 1,
        "frames": frames,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def render_grid_file(path: Path) -> Image.Image:
    payload = json.loads(path.read_text(encoding="utf-8"))
    palette = [hex_to_rgb(value) for value in payload["palette"]]
    frame_width = int(payload["frame_width"])
    frame_height = int(payload["frame_height"])
    columns = int(payload["columns"])
    rows = int(payload["rows"])
    sheet = Image.new("RGBA", (frame_width * columns, frame_height * rows), (0, 0, 0, 0))
    for index, grid in enumerate(payload["frames"]):
        frame = grid_to_image(grid, palette)
        sheet.alpha_composite(
            frame, ((index % columns) * frame_width, (index // columns) * frame_height)
        )
    return sheet
