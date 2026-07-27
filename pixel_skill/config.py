from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASSET_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaletteConfig(StrictModel):
    mode: Literal["profile", "fixed", "adaptive", "semantic"] = "profile"
    colors: list[str] = Field(default_factory=list)
    color_count: int = Field(default=8, ge=1, le=256)
    max_colors: int | None = Field(default=None, ge=1, le=256)
    count_rule: Literal["exact", "maximum"] = "maximum"
    source: Literal["request", "references", "source", "profile"] = "profile"
    roles: dict[str, int] = Field(default_factory=dict)
    role_masks: dict[str, Path] = Field(default_factory=dict)

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            if len(value) != 7 or not value.startswith("#"):
                raise ValueError(f"invalid HEX color: {value}")
            try:
                int(value[1:], 16)
            except ValueError as exc:
                raise ValueError(f"invalid HEX color: {value}") from exc
            upper = value.upper()
            if upper not in normalized:
                normalized.append(upper)
        return normalized

    @model_validator(mode="before")
    @classmethod
    def migrate_max_colors(cls, value):
        if (
            isinstance(value, dict)
            and value.get("max_colors") is not None
            and "color_count" not in value
        ):
            value = dict(value)
            value["color_count"] = value["max_colors"]
        return value

    @model_validator(mode="after")
    def validate_palette(self) -> "PaletteConfig":
        if self.max_colors is not None:
            self.color_count = self.max_colors
        if self.mode == "fixed" and not self.colors:
            raise ValueError("fixed palette requires at least one color")
        if self.mode == "fixed" and len(self.colors) > self.color_count:
            raise ValueError("fixed palette colors exceed color_count")
        if (
            self.count_rule == "exact"
            and self.mode == "fixed"
            and len(self.colors) != self.color_count
        ):
            raise ValueError("exact fixed palette must contain color_count colors")
        if any(value < 1 for value in self.roles.values()):
            raise ValueError("palette role budgets must be positive")
        if self.roles and sum(self.roles.values()) > self.color_count:
            raise ValueError("palette role budgets exceed color_count")
        return self


class AlphaConfig(StrictModel):
    mode: Literal["binary", "opaque"] = "binary"
    transparent_counts_as_color: bool = False


class BackgroundConfig(StrictModel):
    mode: Literal["transparent", "solid", "preserve"] = "transparent"
    color: str = "#000000"

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("background color must be #RRGGBB")
        try:
            int(value[1:], 16)
        except ValueError as exc:
            raise ValueError("background color must be #RRGGBB") from exc
        return value.upper()


class StyleConfig(StrictModel):
    profile: str = "clean_sprite"
    outline: Literal["none", "dark", "light", "automatic", "selective"] = "automatic"
    shading_levels: int = Field(default=2, ge=1, le=8)
    dithering: Literal["off", "none", "ordered-bayer-2", "ordered-bayer-4", "floyd-steinberg"] = (
        "off"
    )


class CompositionConfig(StrictModel):
    subject_scale: float = Field(default=0.8, ge=0.1, le=1.0)
    alignment: Literal["center", "top", "bottom", "left", "right"] = "center"
    padding: int = Field(default=1, ge=0, le=128)


class DownsampleConfig(StrictModel):
    method: Literal["area", "edge_aware"] = "area"


class ReferenceConfig(StrictModel):
    mode: Literal["auto", "explicit", "none"] = "auto"
    paths: list[Path] = Field(default_factory=list)
    category: Literal[
        "character", "npc", "enemy", "boss", "item", "tile", "effect", "ui", "any"
    ] = "any"
    minimum: int = Field(default=3, ge=0, le=12)
    maximum: int = Field(default=6, ge=0, le=12)

    @model_validator(mode="after")
    def validate_references(self) -> "ReferenceConfig":
        if self.minimum > self.maximum:
            raise ValueError("references.minimum cannot exceed references.maximum")
        if self.mode == "explicit" and not self.paths:
            raise ValueError("explicit reference mode requires paths")
        return self


class GenerationConfig(StrictModel):
    provider: Literal["offline", "openai", "codex_imagegen"] = "offline"
    variants: int = Field(default=3, ge=1, le=6)
    candidates: int | None = Field(default=None, ge=1, le=6)
    seed: int | None = None
    allow_image_generation: bool = False
    backend: Literal["local", "openai"] | None = None
    model: str = "gpt-image-2"
    quality: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def migrate_legacy(self) -> "GenerationConfig":
        if self.candidates is not None:
            self.variants = self.candidates
        if self.backend == "openai":
            self.provider = "openai"
        elif self.backend == "local":
            self.provider = "offline"
        return self


class CleanupConfig(StrictModel):
    remove_isolated_pixels: bool = True
    minimum_cluster_size: int = Field(default=2, ge=1, le=4096)
    binary_alpha: bool = True
    connectivity: Literal[4, 8] = 4
    protected_mask: Path | None = None


class AnimationAction(StrictModel):
    name: str
    start: int = Field(ge=0)
    count: int = Field(ge=1)
    fps: int = Field(default=8, ge=1, le=60)


class AnimationConfig(StrictModel):
    frame_width: int = Field(default=32, ge=1, le=512)
    frame_height: int = Field(default=32, ge=1, le=512)
    frame_count: int = Field(default=1, ge=1, le=64)
    columns: int = Field(default=1, ge=1, le=64)
    rows: int = Field(default=1, ge=1, le=64)
    actions: list[AnimationAction] = Field(default_factory=list)
    baseline_tolerance: int = Field(default=2, ge=0, le=32)
    anchor_tolerance: int = Field(default=2, ge=0, le=32)

    @model_validator(mode="after")
    def validate_layout(self) -> "AnimationConfig":
        if self.columns * self.rows < self.frame_count:
            raise ValueError("animation grid has fewer cells than frame_count")
        for action in self.actions:
            if action.start + action.count > self.frame_count:
                raise ValueError(f"animation action {action.name!r} exceeds frame_count")
        return self


class PixelPatch(StrictModel):
    operation: Literal["set_pixel", "fill_rect"]
    color: str | None = None
    transparent: bool = False
    frame: int = Field(default=0, ge=0)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(default=1, ge=1)
    height: int = Field(default=1, ge=1)

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("patch color must be #RRGGBB")
        int(value[1:], 16)
        return value.upper()

    @model_validator(mode="after")
    def validate_fill(self) -> "PixelPatch":
        if not self.transparent and self.color is None:
            raise ValueError("non-transparent patch requires color")
        if self.operation == "set_pixel" and (self.width != 1 or self.height != 1):
            raise ValueError("set_pixel patch must be 1x1")
        return self


class ExportConfig(StrictModel):
    preview_scale: int = Field(default=12, ge=1, le=64)
    save_manifest: bool = True
    save_intermediate: bool = True
    output_dir: Path | None = None
    overwrite: bool = False
    promote: bool = False
    promote_to: Path | None = None
    aseprite: Literal["off", "auto", "required"] = "auto"

    @model_validator(mode="after")
    def validate_promotion(self) -> "ExportConfig":
        if self.promote and self.promote_to is None:
            raise ValueError("export.promote requires export.promote_to")
        if self.promote and not self.save_manifest:
            raise ValueError("export.promote requires export.save_manifest=true")
        return self


class PixelArtRequest(StrictModel):
    schema_version: int = Field(default=2, ge=2, le=2)
    asset_id: str = "pixel_asset"
    description: str = ""
    prompt: str = "pixel art subject"
    asset_type: Literal["static", "tile", "animation"] = "static"
    style_profile: str = "generic"
    project_root: Path | None = None
    project_config: Path | None = None
    width: int = Field(default=32, ge=1, le=512)
    height: int = Field(default=32, ge=1, le=512)
    palette: PaletteConfig = Field(default_factory=PaletteConfig)
    alpha: AlphaConfig = Field(default_factory=AlphaConfig)
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)
    composition: CompositionConfig = Field(default_factory=CompositionConfig)
    downsample: DownsampleConfig = Field(default_factory=DownsampleConfig)
    references: ReferenceConfig = Field(default_factory=ReferenceConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    animation: AnimationConfig = Field(default_factory=AnimationConfig)
    patches: list[PixelPatch] = Field(default_factory=list)
    max_repair_rounds: int = Field(default=2, ge=0, le=2)
    export: ExportConfig = Field(default_factory=ExportConfig)

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, value: str) -> str:
        if not ASSET_ID_RE.fullmatch(value):
            raise ValueError("asset_id must be a valid snake_case identifier")
        return value

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "description" not in data and "prompt" in data:
            data["description"] = data["prompt"]
        if "prompt" not in data and "description" in data:
            data["prompt"] = data["description"]
        if "asset_id" not in data:
            data["asset_id"] = "pixel_asset"
        if "schema_version" not in data:
            data["schema_version"] = 2
        return data

    @model_validator(mode="after")
    def cross_validate(self) -> "PixelArtRequest":
        if self.description:
            self.prompt = self.description
        else:
            self.description = self.prompt
        frame_min = min(self.frame_size)
        if self.composition.padding * 2 >= frame_min:
            raise ValueError("padding leaves no drawable area")
        if self.palette.mode == "fixed" and self.background.mode == "solid":
            if self.background.color not in self.palette.colors:
                raise ValueError("solid background must belong to the fixed palette")
        if self.alpha.mode == "opaque" and self.background.mode == "transparent":
            self.background.mode = "preserve"
        if self.asset_type != "animation" and self.animation.frame_count != 1:
            raise ValueError("frame_count > 1 requires asset_type='animation'")
        if len(self.patches) > 256:
            raise ValueError("too many pixel patches")
        return self

    @property
    def frame_size(self) -> tuple[int, int]:
        if self.asset_type == "animation":
            return self.animation.frame_width, self.animation.frame_height
        return self.width, self.height

    @property
    def output_size(self) -> tuple[int, int]:
        if self.asset_type == "animation":
            return (
                self.animation.frame_width * self.animation.columns,
                self.animation.frame_height * self.animation.rows,
            )
        return self.width, self.height

    @classmethod
    def from_file(cls, path: str | Path) -> "PixelArtRequest":
        source = Path(path)
        text = source.read_text(encoding="utf-8")
        if source.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("request root must be an object")
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "PixelArtRequest":
        return cls.from_file(path)

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


class Manifest(StrictModel):
    schema_version: int = 2
    success: bool
    request: dict
    prompt_plan: dict
    palette: list[str]
    references: list[str] = Field(default_factory=list)
    candidate_scores: list[dict] = Field(default_factory=list)
    frame_manifest: list[dict] = Field(default_factory=list)
    stage_stats: dict = Field(default_factory=dict)
    files: dict[str, dict | str] = Field(default_factory=dict)
    backend: dict = Field(default_factory=dict)
    semantic_review: dict = Field(default_factory=dict)
    promoted_files: dict[str, str] = Field(default_factory=dict)


def write_schemas(directory: str | Path) -> None:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "request.schema.json").write_text(
        json.dumps(PixelArtRequest.model_json_schema(), indent=2), encoding="utf-8"
    )
    (target / "manifest.schema.json").write_text(
        json.dumps(Manifest.model_json_schema(), indent=2), encoding="utf-8"
    )
