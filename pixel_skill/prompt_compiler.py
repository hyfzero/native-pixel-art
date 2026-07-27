from __future__ import annotations

from pydantic import BaseModel, Field

from .config import PixelArtRequest


class PromptPlan(BaseModel):
    subject: str
    silhouette: str
    composition: str
    key_features: list[str] = Field(default_factory=list)
    forbidden_details: list[str] = Field(default_factory=list)
    color_roles: dict[str, int] = Field(default_factory=dict)
    size_adaptations: list[str] = Field(default_factory=list)
    generation_prompt: str
    negative_constraints: list[str] = Field(default_factory=list)
    reference_guidance: str = ""


class PromptCompiler:
    def compile(self, request: PixelArtRequest) -> PromptPlan:
        frame_width, frame_height = request.frame_size
        minimum = min(frame_width, frame_height)
        if minimum <= 8:
            adaptations = [
                "single centered subject with iconic silhouette",
                "omit facial features, fine lines, and complex backgrounds",
                "use two to four large color blocks",
            ]
            forbidden = ["fine facial detail", "thin lines", "texture", "complex background"]
        elif minimum <= 16:
            adaptations = [
                "retain one or two identifying details",
                "render eyes only as high-contrast points",
                "simplify clothing into four to eight color regions",
            ]
            forbidden = ["tiny accessories", "smooth gradients", "dense texture"]
        elif minimum <= 32:
            adaptations = [
                "allow a simple expression and limited clothing detail",
                "limit each material to at most three shades",
                "target six to twelve visually distinct colors",
            ]
            forbidden = ["photorealistic texture", "subpixel detail", "soft gradient background"]
        else:
            adaptations = [
                "prefer connected shapes and controlled color ramps",
                "keep all features readable at native size",
            ]
            forbidden = ["photorealistic noise", "anti-aliased microdetail"]
        if request.style_profile == "game_world_duotone":
            profile_guidance = (
                "Match the project's monochrome game-world language: severe high contrast, "
                "connected silhouette, sparse semantic highlights, no dithering or soft shading."
            )
        elif request.style_profile == "room_color":
            profile_guidance = (
                "Match the project's warm Room-world character and prop references: readable dark "
                "outline, compact warm color ramps, ordinary hand-authored pixel-art proportions."
            )
        else:
            profile_guidance = "Use clean hand-authored pixel-art proportions and connected shapes."
        animation_guidance = ""
        if request.asset_type == "animation":
            animation_guidance = (
                f" Design {request.animation.frame_count} frames in a "
                f"{request.animation.columns}x{request.animation.rows} fixed grid; keep the same "
                "camera, scale, baseline, anchor, palette intent, and unobstructed cell boundaries."
            )
        prompt = (
            f"Create a high-resolution precursor to be deterministically compiled into "
            f"{frame_width}x{frame_height} native pixel art per frame. Subject: {request.prompt}. "
            f"{profile_guidance} Use a strong readable silhouette, large flat color blocks, low "
            f"detail, safe padding, and a plain separable background.{animation_guidance} "
            + " ".join(adaptations)
        )
        return PromptPlan(
            subject=request.prompt,
            silhouette="strong, complete, and recognizable at native resolution",
            composition=f"{request.composition.alignment}; subject scale {request.composition.subject_scale:.2f}; padding {request.composition.padding}px",
            key_features=[
                "complete subject",
                "large connected shapes",
                "clear foreground/background separation",
            ],
            forbidden_details=forbidden,
            color_roles=request.palette.roles,
            size_adaptations=adaptations,
            generation_prompt=prompt,
            negative_constraints=forbidden
            + ["anti-aliasing", "text", "watermark", "excessive gradients"],
            reference_guidance=profile_guidance,
        )
