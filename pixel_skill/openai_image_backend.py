from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from .image_backend import (
    BackendConfigurationError,
    ImageBackendError,
    UnsupportedBackendOptionError,
)


class OpenAIImageBackend:
    def __init__(
        self,
        model: str = "gpt-image-2",
        quality: str = "medium",
        metadata_dir: str | Path | None = None,
        client: Any | None = None,
    ) -> None:
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise BackendConfigurationError("OPENAI_API_KEY is not set")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise BackendConfigurationError(
                    "install the optional dependency: pip install native-pixel-art[openai]"
                ) from exc
            client = OpenAI()
        self.client = client
        self.model = model
        self.quality = quality
        self.metadata_dir = Path(metadata_dir) if metadata_dir else None
        self.records: list[dict] = []

    @staticmethod
    def _decode(response: Any) -> Image.Image:
        try:
            encoded = response.data[0].b64_json
            return Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGBA")
        except Exception as exc:
            raise ImageBackendError(
                "OpenAI response did not contain a readable base64 image"
            ) from exc

    @staticmethod
    def _response_dict(response: Any) -> dict:
        if hasattr(response, "model_dump"):
            return response.model_dump(mode="json")
        if isinstance(response, dict):
            return response
        return {"repr": repr(response)}

    def _record(self, operation: str, params: dict, response: Any, index: int) -> None:
        record = {
            "operation": operation,
            "parameters": params,
            "response": self._response_dict(response),
        }
        self.records.append(record)
        if self.metadata_dir:
            self.metadata_dir.mkdir(parents=True, exist_ok=True)
            (self.metadata_dir / f"openai_{operation}_{index}.json").write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def generate(
        self,
        prompt: str,
        variants: int,
        seed: int | None = None,
        references: list[Path] | None = None,
    ) -> list[Image.Image]:
        if seed is not None:
            raise UnsupportedBackendOptionError(
                "gpt-image-2 does not document seed support; refusing to claim deterministic generation"
            )
        images: list[Image.Image] = []
        for index in range(variants):
            try:
                if references:
                    handles = [path.open("rb") for path in references]
                    try:
                        params = {
                            "model": self.model,
                            "image": handles,
                            "prompt": prompt,
                            "quality": self.quality,
                            "size": "1024x1024",
                        }
                        response = self.client.images.edit(**params)
                    finally:
                        for handle in handles:
                            handle.close()
                    operation = "edit"
                else:
                    params = {
                        "model": self.model,
                        "prompt": prompt,
                        "quality": self.quality,
                        "size": "1024x1024",
                    }
                    response = self.client.images.generate(**params)
                    operation = "generate"
            except Exception as exc:
                raise ImageBackendError(f"OpenAI image generation failed: {exc}") from exc
            record_params = {key: value for key, value in params.items() if key != "image"}
            if references:
                record_params["references"] = [str(path) for path in references]
            self._record(operation, record_params, response, index)
            images.append(self._decode(response))
        return images

    def edit(self, image: Image.Image, prompt: str, mask: Image.Image | None = None) -> Image.Image:
        image_buffer = io.BytesIO()
        image.convert("RGBA").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        image_buffer.name = "image.png"  # type: ignore[attr-defined]
        params: dict[str, Any] = {
            "model": self.model,
            "image": image_buffer,
            "prompt": prompt,
            "quality": self.quality,
        }
        if mask is not None:
            mask_buffer = io.BytesIO()
            mask.convert("RGBA").save(mask_buffer, format="PNG")
            mask_buffer.seek(0)
            mask_buffer.name = "mask.png"  # type: ignore[attr-defined]
            params["mask"] = mask_buffer
        try:
            response = self.client.images.edit(**params)
        except Exception as exc:
            raise ImageBackendError(f"OpenAI image edit failed: {exc}") from exc
        record_params = {
            key: value for key, value in params.items() if key not in {"image", "mask"}
        }
        self._record("edit", record_params, response, len(self.records))
        return self._decode(response)
