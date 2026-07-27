from __future__ import annotations

import numpy as np
from PIL import Image

from .palette import srgb_to_lab

BAYER_2 = np.array([[0, 2], [3, 1]], dtype=np.float32)
BAYER_4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)


def _nearest_indices(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    pixels_lab = srgb_to_lab(rgb.reshape(-1, 3))
    palette_lab = srgb_to_lab(palette)
    distance = np.sum((pixels_lab[:, None, :] - palette_lab[None, :, :]) ** 2, axis=2)
    return np.argmin(distance, axis=1).reshape(rgb.shape[:2])


def _ordered_adjust(rgb: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    tiled = np.tile(
        matrix, (int(np.ceil(height / matrix.shape[0])), int(np.ceil(width / matrix.shape[1])))
    )
    tiled = tiled[:height, :width]
    threshold = ((tiled + 0.5) / matrix.size - 0.5) * 24.0
    return np.clip(rgb.astype(np.float32) + threshold[..., None], 0, 255).astype(np.uint8)


def _floyd_steinberg(rgb: np.ndarray, alpha: np.ndarray, palette: np.ndarray) -> np.ndarray:
    work = rgb.astype(np.float32).copy()
    output = np.zeros_like(rgb)
    palette_float = palette.astype(np.float32)
    height, width = rgb.shape[:2]
    for y in range(height):
        for x in range(width):
            if alpha[y, x] == 0:
                continue
            lab = srgb_to_lab(np.clip(work[y, x], 0, 255)[None, :])[0]
            pal_lab = srgb_to_lab(palette)
            index = int(np.argmin(np.sum((pal_lab - lab) ** 2, axis=1)))
            chosen = palette_float[index]
            output[y, x] = chosen.astype(np.uint8)
            error = work[y, x] - chosen
            current_luma = float(np.mean(work[y, x]))
            for dx, dy, factor in ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height and alpha[ny, nx] > 0:
                    if abs(float(np.mean(work[ny, nx])) - current_luma) < 80:
                        work[ny, nx] += error * factor
    return output


def quantize_image(
    image: Image.Image, palette: list[tuple[int, int, int]], dithering: str = "off"
) -> Image.Image:
    if not palette:
        raise ValueError("palette cannot be empty")
    rgba = np.asarray(image.convert("RGBA")).copy()
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    palette_array = np.asarray(palette, dtype=np.uint8)
    if dithering == "ordered-bayer-2":
        source = _ordered_adjust(rgb, BAYER_2)
        indices = _nearest_indices(source, palette_array)
        result = palette_array[indices]
    elif dithering == "ordered-bayer-4":
        source = _ordered_adjust(rgb, BAYER_4)
        indices = _nearest_indices(source, palette_array)
        result = palette_array[indices]
    elif dithering == "floyd-steinberg":
        result = _floyd_steinberg(rgb, alpha, palette_array)
    else:
        indices = _nearest_indices(rgb, palette_array)
        result = palette_array[indices]
    result[alpha == 0] = 0
    return Image.fromarray(np.dstack([result, alpha]).astype(np.uint8), "RGBA")
