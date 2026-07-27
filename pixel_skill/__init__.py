"""Strict, deterministic pixel-art compilation."""

from .config import PixelArtRequest
from .pipeline import CompileResult, compile_image
from .validator import ValidationReport, validate_image

__all__ = [
    "CompileResult",
    "PixelArtRequest",
    "ValidationReport",
    "compile_image",
    "validate_image",
]

__version__ = "0.1.0"
