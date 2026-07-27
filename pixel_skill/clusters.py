from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image


def _neighbors(x: int, y: int, width: int, height: int, connectivity: int):
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if connectivity == 8:
        offsets += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    for dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if 0 <= nx < width and 0 <= ny < height:
            yield nx, ny


def find_components(image: Image.Image, connectivity: int = 4) -> list[dict]:
    rgba = np.asarray(image.convert("RGBA"))
    height, width = rgba.shape[:2]
    visited = np.zeros((height, width), dtype=bool)
    components: list[dict] = []
    for y in range(height):
        for x in range(width):
            if visited[y, x] or rgba[y, x, 3] == 0:
                continue
            color = tuple(int(v) for v in rgba[y, x, :3])
            queue = deque([(x, y)])
            visited[y, x] = True
            pixels: list[tuple[int, int]] = []
            while queue:
                px, py = queue.popleft()
                pixels.append((px, py))
                for nx, ny in _neighbors(px, py, width, height, connectivity):
                    if (
                        not visited[ny, nx]
                        and rgba[ny, nx, 3] > 0
                        and tuple(rgba[ny, nx, :3]) == color
                    ):
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            components.append({"color": color, "size": len(pixels), "pixels": pixels})
    return components


def cleanup_clusters(
    image: Image.Image,
    minimum_size: int = 2,
    connectivity: int = 4,
    protected_mask: Image.Image | None = None,
) -> tuple[Image.Image, dict]:
    rgba = np.asarray(image.convert("RGBA")).copy()
    protected = None
    if protected_mask is not None:
        protected = (
            np.asarray(protected_mask.convert("L").resize(image.size, Image.Resampling.NEAREST)) > 0
        )
    before = find_components(image, connectivity)
    removed = 0
    height, width = rgba.shape[:2]
    for component in before:
        if component["size"] >= minimum_size:
            continue
        pixels = component["pixels"]
        if protected is not None and any(protected[y, x] for x, y in pixels):
            continue
        adjacent: list[tuple[int, int, int]] = []
        for x, y in pixels:
            for nx, ny in _neighbors(x, y, width, height, connectivity):
                if (nx, ny) not in pixels and rgba[ny, nx, 3] > 0:
                    adjacent.append(tuple(int(v) for v in rgba[ny, nx, :3]))
        if adjacent:
            original = np.array(component["color"], dtype=np.float32)
            choices = np.unique(np.array(adjacent, dtype=np.uint8), axis=0)
            replacement = choices[
                np.argmin(np.sum((choices.astype(np.float32) - original) ** 2, axis=1))
            ]
            for x, y in pixels:
                rgba[y, x, :3] = replacement
            removed += len(pixels)
        else:
            for x, y in pixels:
                rgba[y, x] = (0, 0, 0, 0)
            removed += len(pixels)
    result = Image.fromarray(rgba, "RGBA")
    after = find_components(result, connectivity)
    return result, {
        "components_before": len(before),
        "components_after": len(after),
        "small_pixels_merged": removed,
        "isolated_before": sum(1 for component in before if component["size"] == 1),
        "outline_break_warning": sum(1 for component in after if component["size"] == 1) > 0,
    }
