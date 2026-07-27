from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .config import PixelArtRequest
from .crop import foreground_bbox
from .downsample import downsample


def score_candidate(image: Image.Image, request: PixelArtRequest, index: int = 0) -> dict:
    rgba = image.convert("RGBA")
    bbox = foreground_bbox(rgba)
    trial = downsample(rgba, request.frame_size, "area")
    array = np.asarray(trial)
    visible = array[..., 3] > 8
    coverage = float(visible.mean())
    touches = bool(
        np.any(visible[0]) or np.any(visible[-1]) or np.any(visible[:, 0]) or np.any(visible[:, -1])
    )
    if np.any(visible):
        colors = array[..., :3][visible].astype(np.float32)
        contrast = min(1.0, float(np.std(colors)) / 90.0)
        unique_ratio = min(
            1.0,
            len(np.unique(colors.astype(np.uint8), axis=0))
            / max(2, request.palette.color_count * 4),
        )
    else:
        contrast = 0.0
        unique_ratio = 1.0
    edges = np.asarray(trial.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    edge_density = float(np.mean(edges > 32))
    scale_score = max(0.0, 1.0 - abs(coverage - request.composition.subject_scale**2))
    score = (
        0.28 * scale_score
        + 0.22 * contrast
        + 0.18 * (not touches)
        + 0.16 * (1 - unique_ratio)
        + 0.16 * (1 - min(1.0, edge_density * 2))
    )
    return {
        "index": index,
        "score": round(float(score), 6),
        "subject_complete": bbox is not None and not touches,
        "safe_padding": not touches,
        "coverage": round(coverage, 6),
        "contrast": round(contrast, 6),
        "color_complexity": round(unique_ratio, 6),
        "edge_density": round(edge_density, 6),
        "structure_loss": round(min(1.0, edge_density * 2), 6),
    }


def select_candidate(
    images: list[Image.Image], request: PixelArtRequest
) -> tuple[Image.Image, list[dict]]:
    if not images:
        raise ValueError("no image candidates")
    scores = [score_candidate(image, request, index) for index, image in enumerate(images)]
    best = max(scores, key=lambda item: (item["score"], -item["index"]))
    return images[int(best["index"])], scores
