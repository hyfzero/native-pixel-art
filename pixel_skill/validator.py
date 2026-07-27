from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from .clusters import find_components
from .config import PixelArtRequest
from .palette import hex_to_rgb, rgb_to_hex


@dataclass
class ValidationReport:
    success: bool = True
    hard_failures: list[dict] = field(default_factory=list)
    soft_warnings: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def hard(self, code: str, message: str) -> None:
        self.success = False
        self.hard_failures.append({"code": code, "message": message})

    def warn(self, code: str, message: str) -> None:
        self.soft_warnings.append({"code": code, "message": message})

    def to_dict(self) -> dict:
        return asdict(self)


def _load_image(image_or_path: Image.Image | str | Path) -> tuple[Image.Image, str | None]:
    if isinstance(image_or_path, Image.Image):
        return image_or_path.convert("RGBA"), image_or_path.format
    with Image.open(image_or_path) as loaded:
        loaded.load()
        return loaded.convert("RGBA"), loaded.format


def _frame_metrics(frame: np.ndarray, index: int) -> dict:
    visible = frame[..., 3] > 0
    if not np.any(visible):
        return {"frame": index, "empty": True, "anchor_x": None, "baseline": None}
    ys, xs = np.where(visible)
    colors = np.unique(frame[..., :3][visible], axis=0)
    return {
        "frame": index,
        "empty": False,
        "anchor_x": round(float((int(xs.min()) + int(xs.max())) / 2), 3),
        "baseline": int(ys.max()),
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
        "palette": [rgb_to_hex(color) for color in colors],
    }


def _validate_animation(
    rgba: np.ndarray, request: PixelArtRequest, report: ValidationReport
) -> None:
    frame_width, frame_height = request.frame_size
    metrics: list[dict] = []
    for index in range(request.animation.columns * request.animation.rows):
        x = (index % request.animation.columns) * frame_width
        y = (index // request.animation.columns) * frame_height
        frame = rgba[y : y + frame_height, x : x + frame_width]
        item = _frame_metrics(frame, index)
        metrics.append(item)
        if index < request.animation.frame_count and item["empty"]:
            report.hard("empty_animation_frame", f"animation frame {index} is empty")
        if index >= request.animation.frame_count and not item["empty"]:
            report.hard(
                "content_outside_frame_count", f"unused animation cell {index} contains pixels"
            )
    used = metrics[: request.animation.frame_count]
    anchors = [float(item["anchor_x"]) for item in used if not item["empty"]]
    baselines = [int(item["baseline"]) for item in used if not item["empty"]]
    if anchors and max(anchors) - min(anchors) > request.animation.anchor_tolerance * 2:
        report.hard(
            "anchor_drift",
            f"frame anchors span {max(anchors) - min(anchors):.3f}px; "
            f"allowed ±{request.animation.anchor_tolerance}px",
        )
    if baselines and max(baselines) - min(baselines) > request.animation.baseline_tolerance * 2:
        report.hard(
            "baseline_drift",
            f"frame baselines span {max(baselines) - min(baselines)}px; "
            f"allowed ±{request.animation.baseline_tolerance}px",
        )
    report.metrics["frames"] = used


def _validate_preview(
    image: Image.Image,
    preview: Image.Image | str | Path,
    request: PixelArtRequest,
    report: ValidationReport,
) -> None:
    try:
        preview_image, preview_format = _load_image(preview)
    except (OSError, UnidentifiedImageError) as exc:
        report.hard("unreadable_preview", str(exc))
        return
    expected_size = (
        request.output_size[0] * request.export.preview_scale,
        request.output_size[1] * request.export.preview_scale,
    )
    if preview_image.size != expected_size:
        report.hard(
            "wrong_preview_dimensions",
            f"expected preview {expected_size}, got {preview_image.size}",
        )
        return
    if preview_format not in {None, "PNG"}:
        report.hard("preview_not_png", f"preview format is {preview_format}")
    expected = image.resize(expected_size, Image.Resampling.NEAREST)
    if not np.array_equal(np.asarray(preview_image), np.asarray(expected)):
        report.hard(
            "preview_not_nearest_neighbor",
            "preview pixels do not exactly match integer nearest-neighbor scaling",
        )


def validate_image(
    image_or_path: Image.Image | str | Path,
    request: PixelArtRequest,
    preview: Image.Image | str | Path | None = None,
) -> ValidationReport:
    """Reload and validate a PNG without calling any compiler or repair function."""
    report = ValidationReport()
    try:
        image, image_format = _load_image(image_or_path)
    except (OSError, UnidentifiedImageError) as exc:
        report.hard("unreadable_png", str(exc))
        return report
    if image_format not in {None, "PNG"}:
        report.hard("not_png", f"expected PNG, got {image_format}")
    if image.size != request.output_size:
        report.hard(
            "wrong_dimensions",
            f"expected {request.output_size[0]}x{request.output_size[1]}, "
            f"got {image.width}x{image.height}",
        )

    rgba = np.asarray(image)
    visible = rgba[..., 3] > 0
    colors = (
        np.unique(rgba[..., :3][visible], axis=0)
        if np.any(visible)
        else np.empty((0, 3), dtype=np.uint8)
    )
    visible_count = int(len(colors))
    counted_colors = visible_count + (
        1 if request.alpha.transparent_counts_as_color and np.any(~visible) else 0
    )
    actual_hex = [rgb_to_hex(color) for color in colors]
    report.metrics["visible_colors"] = visible_count
    report.metrics["counted_colors"] = counted_colors
    report.metrics["palette"] = actual_hex
    if request.palette.count_rule == "exact":
        if counted_colors != request.palette.color_count:
            report.hard(
                "wrong_color_count",
                f"expected exactly {request.palette.color_count} counted colors, got {counted_colors}",
            )
    elif counted_colors > request.palette.color_count:
        report.hard(
            "too_many_colors",
            f"{counted_colors} exceeds color_count={request.palette.color_count}",
        )

    if request.palette.mode == "fixed":
        allowed = {hex_to_rgb(value) for value in request.palette.colors}
        used = {tuple(int(value) for value in color) for color in colors}
        extras = [
            rgb_to_hex(color) for color in colors if tuple(int(v) for v in color) not in allowed
        ]
        if extras:
            report.hard("palette_violation", f"illegal visible colors: {extras}")
        if request.palette.count_rule == "exact":
            missing = [rgb_to_hex(color) for color in sorted(allowed - used)]
            if missing:
                report.hard(
                    "unused_required_colors",
                    f"required colors are not meaningfully present: {missing}",
                )

    alpha_values = np.unique(rgba[..., 3])
    report.metrics["alpha_values"] = [int(value) for value in alpha_values]
    if any(value not in (0, 255) for value in alpha_values):
        report.hard("non_binary_alpha", f"alpha values include {alpha_values.tolist()}")
    if request.alpha.mode == "opaque" and np.any(rgba[..., 3] != 255):
        report.hard("not_opaque", "opaque alpha mode forbids transparent pixels")
    transparent = rgba[..., 3] == 0
    if np.any(rgba[..., :3][transparent] != 0):
        report.hard("transparent_rgb_nonzero", "transparent pixels must have RGB 0,0,0")

    if request.asset_type == "animation" and image.size == request.output_size:
        _validate_animation(rgba, request, report)
    if preview is not None:
        _validate_preview(image, preview, request, report)

    if np.any(visible):
        ys, xs = np.where(visible)
        touches = (
            xs.min() == 0
            or ys.min() == 0
            or xs.max() == image.width - 1
            or ys.max() == image.height - 1
        )
        coverage = float(visible.mean())
        report.metrics["coverage"] = coverage
        if touches:
            report.warn("subject_touches_border", "visible subject touches the image border")
        if coverage < 0.03 or coverage > 0.95:
            report.warn("unusual_coverage", f"visible coverage is {coverage:.3f}")
        components = find_components(image, request.cleanup.connectivity)
        small = sum(
            1
            for component in components
            if component["size"] < request.cleanup.minimum_cluster_size
        )
        report.metrics["components"] = len(components)
        if small:
            report.warn("small_clusters", f"{small} clusters are below minimum size")
    else:
        report.hard("empty_image", "final image contains no visible pixels")
    return report
