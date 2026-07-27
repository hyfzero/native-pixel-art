from __future__ import annotations

from PIL import Image

from .config import PixelArtRequest
from .validator import ValidationReport


def review(image: Image.Image, request: PixelArtRequest, validation: ValidationReport) -> dict:
    warnings = [item["code"] for item in validation.soft_warnings]
    return {
        "mode": "heuristic-only",
        "complete_semantic_understanding": False,
        "native_size_readable": "unusual_coverage" not in warnings,
        "safe_padding": "subject_touches_border" not in warnings,
        "palette_role_masks_used": bool(request.palette.role_masks),
        "notes": [
            "No external vision model was used for semantic review.",
            "Results are based on coverage, border, palette, and connectivity metrics.",
        ],
    }
