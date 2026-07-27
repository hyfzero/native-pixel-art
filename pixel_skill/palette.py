from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from PIL import Image


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"invalid HEX color: {value}")
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"invalid HEX color: {value}") from exc


def rgb_to_hex(rgb: tuple[int, int, int] | np.ndarray) -> str:
    return "#" + "".join(f"{int(c):02X}" for c in rgb)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)
    matrix = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = linear @ matrix.T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def extract_palette(image: Image.Image, colors: int) -> list[tuple[int, int, int]]:
    rgba = np.asarray(image.convert("RGBA"))
    pixels = rgba[..., :3][rgba[..., 3] > 0]
    if len(pixels) == 0:
        return [(0, 0, 0)]
    unique, counts = np.unique(pixels, axis=0, return_counts=True)
    if len(unique) <= colors:
        order = np.argsort(-counts, kind="stable")
        return [tuple(map(int, unique[i])) for i in order]

    labs = srgb_to_lab(unique)
    weights = counts.astype(np.float64)
    centers = [int(np.argmax(weights))]
    while len(centers) < colors:
        distances = np.min(
            np.sum((labs[:, None, :] - labs[np.array(centers)][None, :, :]) ** 2, axis=2), axis=1
        )
        score = distances * np.sqrt(weights)
        score[np.array(centers)] = -1
        centers.append(int(np.argmax(score)))

    center_labs = labs[np.array(centers)].copy()
    for _ in range(20):
        labels = np.argmin(np.sum((labs[:, None] - center_labs[None]) ** 2, axis=2), axis=1)
        updated = center_labs.copy()
        for index in range(colors):
            mask = labels == index
            if np.any(mask):
                updated[index] = np.average(labs[mask], axis=0, weights=weights[mask])
        if np.allclose(updated, center_labs, atol=1e-4):
            break
        center_labs = updated
    labels = np.argmin(np.sum((labs[:, None] - center_labs[None]) ** 2, axis=2), axis=1)
    result: list[tuple[int, int, int]] = []
    cluster_weights: list[float] = []
    for index in range(colors):
        mask = labels == index
        if np.any(mask):
            mean = np.average(unique[mask], axis=0, weights=weights[mask])
            result.append(tuple(int(round(c)) for c in np.clip(mean, 0, 255)))
            cluster_weights.append(float(weights[mask].sum()))
    order = np.argsort(-np.asarray(cluster_weights), kind="stable")
    return [result[int(i)] for i in order]


def extract_palette_from_images(
    images: list[Image.Image],
    colors: int,
) -> list[tuple[int, int, int]]:
    """Extract one deterministic Lab palette without letting image dimensions bias it."""
    samples: list[np.ndarray] = []
    per_image = max(colors * 32, 1024)
    for image in images:
        rgba = np.asarray(image.convert("RGBA"))
        pixels = rgba[..., :3][rgba[..., 3] > 0]
        if not len(pixels):
            continue
        unique, counts = np.unique(pixels, axis=0, return_counts=True)
        order = np.argsort(-counts, kind="stable")
        ranked = unique[order]
        if len(ranked) > per_image:
            ranked = ranked[:per_image]
        samples.append(ranked)
    if not samples:
        return [(0, 0, 0)]
    merged = np.concatenate(samples, axis=0)
    synthetic = Image.fromarray(
        np.dstack(
            [
                merged.reshape(1, -1, 3),
                np.full((1, len(merged)), 255, dtype=np.uint8),
            ]
        ),
        "RGBA",
    )
    return extract_palette(synthetic, colors)


def _used_palette_indices(
    images: list[Image.Image],
    palette: list[tuple[int, int, int]],
) -> set[int]:
    palette_lab = srgb_to_lab(np.asarray(palette, dtype=np.uint8))
    used: set[int] = set()
    for image in images:
        rgba = np.asarray(image.convert("RGBA"))
        pixels = rgba[..., :3][rgba[..., 3] > 0]
        if not len(pixels):
            continue
        unique = np.unique(pixels, axis=0)
        labs = srgb_to_lab(unique)
        distances = np.sum(
            (labs[:, None, :] - palette_lab[None, :, :]) ** 2,
            axis=2,
        )
        used.update(map(int, np.argmin(distances, axis=1)))
    return used


def select_reference_palette_for_source(
    reference_images: list[Image.Image],
    source_images: list[Image.Image],
    colors: int,
) -> list[tuple[int, int, int]]:
    """Choose reference-derived colors that remain distinguishable in this source.

    Source Lab clusters are used only as anchors. Each anchor first selects a unique
    nearby project-reference candidate. If two reference candidates collapse to the
    same quantized region, the unused entry is replaced by its meaningful source
    anchor instead of inserting a synthetic pixel into the output.
    """
    anchors = extract_palette_from_images(source_images, colors)
    if len(anchors) < colors:
        return extract_palette_from_images(reference_images, colors)
    pool = extract_palette_from_images(
        reference_images,
        min(256, max(colors * 4, colors)),
    )
    if len(pool) < colors:
        return anchors

    anchor_lab = srgb_to_lab(np.asarray(anchors, dtype=np.uint8))
    pool_lab = srgb_to_lab(np.asarray(pool, dtype=np.uint8))
    distances = np.sum(
        (anchor_lab[:, None, :] - pool_lab[None, :, :]) ** 2,
        axis=2,
    )
    claimed: set[int] = set()
    palette: list[tuple[int, int, int]] = []
    for anchor_index in range(colors):
        for candidate_index in np.argsort(distances[anchor_index], kind="stable"):
            index = int(candidate_index)
            if index not in claimed:
                claimed.add(index)
                palette.append(pool[index])
                break

    for _ in range(colors * 2):
        used = _used_palette_indices(source_images, palette)
        if len(used) == colors:
            break
        baseline = len(used)
        improved = False
        for missing in (index for index in range(colors) if index not in used):
            preferred = [anchors[missing], *anchors]
            for replacement in preferred:
                if replacement in palette and replacement != palette[missing]:
                    continue
                trial = list(palette)
                trial[missing] = replacement
                trial_used = _used_palette_indices(source_images, trial)
                if len(trial_used) > baseline:
                    palette = trial
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return palette


def load_palette(path: str | Path) -> list[str]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    values = data["colors"] if isinstance(data, dict) else data
    return [rgb_to_hex(hex_to_rgb(value)) for value in values]
