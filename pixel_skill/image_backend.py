from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image


class ImageBackendError(RuntimeError):
    """Base error for image generation backends."""


class BackendConfigurationError(ImageBackendError):
    """Raised when a backend is unavailable or incorrectly configured."""


class UnsupportedBackendOptionError(ImageBackendError):
    """Raised when a backend cannot honor an explicitly requested option."""


@runtime_checkable
class ImageBackend(Protocol):
    def generate(
        self,
        prompt: str,
        variants: int,
        seed: int | None = None,
        references: list[Path] | None = None,
    ) -> list[Image.Image]: ...

    def edit(
        self, image: Image.Image, prompt: str, mask: Image.Image | None = None
    ) -> Image.Image: ...


class LocalImageBackend:
    """Offline backend marker. Local source images are passed to the compiler directly."""

    def generate(
        self,
        prompt: str,
        variants: int,
        seed: int | None = None,
        references: list[Path] | None = None,
    ) -> list[Image.Image]:
        raise BackendConfigurationError(
            "local backend cannot generate images; use `pixel-art compile SOURCE`"
        )

    def edit(self, image: Image.Image, prompt: str, mask: Image.Image | None = None) -> Image.Image:
        raise BackendConfigurationError(
            "local backend cannot edit images; compile the local source instead"
        )


def __getattr__(name: str):
    if name == "OpenAIImageBackend":
        from .openai_image_backend import OpenAIImageBackend

        return OpenAIImageBackend
    raise AttributeError(name)
