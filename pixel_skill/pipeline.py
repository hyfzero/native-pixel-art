from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .animation import animation_metrics, split_source_frames
from .candidate_selector import select_candidate
from .clusters import cleanup_clusters
from .config import Manifest, PixelArtRequest
from .crop import crop_subject, place_subject
from .doctor import find_aseprite
from .downsample import downsample
from .exporter import describe_palette, export_images, sha256_file, write_json
from .grid import apply_patches, image_to_grid, render_grid_file, write_grid
from .image_backend import BackendConfigurationError
from .palette import (
    extract_palette,
    extract_palette_from_images,
    hex_to_rgb,
    select_reference_palette_for_source,
)
from .project import (
    ProjectContext,
    resolve_output_dir,
    resolve_project_path,
    resolve_request,
)
from .promotion import preflight_promotion, promote_outputs
from .prompt_compiler import PromptCompiler
from .quantize import quantize_image
from .references import select_references, write_reference_artifacts
from .semantic_review import review
from .validator import ValidationReport, validate_image


@dataclass
class CompileResult:
    success: bool
    image: Image.Image
    palette: list[tuple[int, int, int]]
    output_dir: Path
    manifest: dict
    validation: ValidationReport


def _transparent_background(image: Image.Image) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA")).copy()
    if np.all(rgba[..., 3] == 255):
        border = np.concatenate(
            [
                rgba[0, :, :3],
                rgba[-1, :, :3],
                rgba[:, 0, :3],
                rgba[:, -1, :3],
            ],
            axis=0,
        )
        background = np.median(border.astype(np.float32), axis=0)
        border_distance = np.sqrt(np.sum((border.astype(np.float32) - background) ** 2, axis=1))
        threshold = float(np.clip(np.percentile(border_distance, 95) + 16.0, 32.0, 96.0))
        distance = np.sqrt(np.sum((rgba[..., :3].astype(np.float32) - background) ** 2, axis=2))
        foreground = distance > threshold
        if np.any(foreground):
            rgba[..., 3][~foreground] = 0
    rgba[..., :3][rgba[..., 3] == 0] = 0
    return Image.fromarray(rgba, "RGBA")


def _normalize_alpha(
    image: Image.Image,
    request: PixelArtRequest,
) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA")).copy()
    if request.alpha.mode == "opaque":
        color = np.asarray(hex_to_rgb(request.background.color), dtype=np.float32)
        alpha = rgba[..., 3:4].astype(np.float32) / 255.0
        rgba[..., :3] = np.rint(rgba[..., :3] * alpha + color * (1.0 - alpha)).astype(np.uint8)
        rgba[..., 3] = 255
    else:
        rgba[..., 3] = np.where(rgba[..., 3] >= 128, 255, 0).astype(np.uint8)
        rgba[..., :3][rgba[..., 3] == 0] = 0
    return Image.fromarray(rgba, "RGBA")


def _apply_background(image: Image.Image, request: PixelArtRequest) -> Image.Image:
    if request.background.mode == "transparent":
        return _transparent_background(image)
    if request.background.mode == "solid":
        color = hex_to_rgb(request.background.color)
        background = Image.new("RGBA", image.size, (*color, 255))
        background.alpha_composite(image.convert("RGBA"))
        return background
    return image.convert("RGBA")


def _reduce_frame(
    frame: Image.Image,
    request: PixelArtRequest,
    index: int,
    intermediate: Path | None,
) -> tuple[Image.Image, dict]:
    prepared = _apply_background(frame, request)
    subject, crop_stats = crop_subject(prepared)
    if intermediate:
        subject.save(intermediate / f"frame_{index:02d}_01_cropped.png")
    frame_width, frame_height = request.frame_size
    work_size = (
        max(frame_width * 4, subject.width),
        max(frame_height * 4, subject.height),
    )
    placed, placement_stats = place_subject(
        subject,
        work_size,
        request.composition.subject_scale,
        request.composition.padding * 4,
        request.composition.alignment,
    )
    reduced = downsample(placed, request.frame_size, request.downsample.method)
    reduced = _apply_background(reduced, request)
    reduced = _normalize_alpha(reduced, request)
    if intermediate:
        reduced.save(intermediate / f"frame_{index:02d}_02_downsampled.png")
    return reduced, {"frame": index, "crop": crop_stats, "placement": placement_stats}


def _choose_palette(
    frames: list[Image.Image],
    request: PixelArtRequest,
    reference_paths: list[Path],
    context: ProjectContext | None,
) -> list[tuple[int, int, int]]:
    if request.palette.mode == "fixed":
        return [hex_to_rgb(value) for value in request.palette.colors]
    if request.palette.mode == "semantic" and request.palette.roles and request.palette.role_masks:
        selected: list[tuple[int, int, int]] = []
        sheet = frames[0] if len(frames) == 1 else _stack_frames_for_palette(frames)
        rgba = np.asarray(sheet.convert("RGBA")).copy()
        for role, budget in request.palette.roles.items():
            mask_path = request.palette.role_masks.get(role)
            if mask_path is None:
                continue
            mask_path = resolve_project_path(mask_path, context)
            mask = (
                np.asarray(
                    Image.open(mask_path).convert("L").resize(sheet.size, Image.Resampling.NEAREST)
                )
                > 0
            )
            role_rgba = rgba.copy()
            role_rgba[..., 3][~mask] = 0
            for color in extract_palette(Image.fromarray(role_rgba, "RGBA"), budget):
                if color not in selected:
                    selected.append(color)
        if len(selected) < request.palette.color_count:
            for color in extract_palette(sheet, request.palette.color_count):
                if color not in selected:
                    selected.append(color)
                if len(selected) >= request.palette.color_count:
                    break
        if selected:
            return selected[: request.palette.color_count]
    if request.palette.source == "references" and reference_paths:
        images: list[Image.Image] = []
        for path in reference_paths:
            with Image.open(path) as image:
                images.append(image.convert("RGBA"))
        if request.palette.count_rule == "exact":
            return select_reference_palette_for_source(
                images,
                frames,
                request.palette.color_count,
            )
        return extract_palette_from_images(images, request.palette.color_count)
    return extract_palette_from_images(frames, request.palette.color_count)


def _stack_frames_for_palette(frames: list[Image.Image]) -> Image.Image:
    width = sum(frame.width for frame in frames)
    height = max(frame.height for frame in frames)
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for frame in frames:
        sheet.alpha_composite(frame, (x, 0))
        x += frame.width
    return sheet


def _quantize_frame(
    frame: Image.Image,
    palette: list[tuple[int, int, int]],
    request: PixelArtRequest,
    index: int,
    intermediate: Path | None,
    context: ProjectContext | None,
) -> tuple[Image.Image, dict]:
    quantized = quantize_image(frame, palette, request.style.dithering)
    if intermediate:
        quantized.save(intermediate / f"frame_{index:02d}_03_quantized.png")
    cleaned = quantized
    cleanup_stats: dict = {"frame": index, "enabled": request.cleanup.remove_isolated_pixels}
    if request.cleanup.remove_isolated_pixels:
        protected = None
        if request.cleanup.protected_mask:
            protected = Image.open(resolve_project_path(request.cleanup.protected_mask, context))
        cleaned, cluster_stats = cleanup_clusters(
            quantized,
            request.cleanup.minimum_cluster_size,
            request.cleanup.connectivity,
            protected,
        )
        cleanup_stats.update(cluster_stats)
    cleaned = _normalize_alpha(cleaned, request)
    if intermediate:
        cleaned.save(intermediate / f"frame_{index:02d}_04_cleaned.png")
    return cleaned, cleanup_stats


def _safe_publish(staging: Path, output_dir: Path, overwrite: bool) -> None:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(f"output directory already exists: {output_dir}")
    backup = output_dir.with_name(f".{output_dir.name}.backup-{uuid.uuid4().hex}")
    if output_dir.exists():
        output_dir.replace(backup)
    try:
        staging.replace(output_dir)
    except Exception:
        if backup.exists() and not output_dir.exists():
            backup.replace(output_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _export_aseprite(output_dir: Path, request: PixelArtRequest) -> tuple[Path | None, str | None]:
    if request.export.aseprite == "off":
        return None, None
    executable = find_aseprite()
    if executable is None:
        message = "Aseprite was not found"
        if request.export.aseprite == "required":
            raise RuntimeError(message)
        return None, message
    target = output_dir / f"{request.asset_id}.aseprite"
    process = subprocess.run(
        [str(executable), "-b", str(output_dir / "final.png"), "--save-as", str(target)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if process.returncode != 0 or not target.exists():
        message = (process.stderr or process.stdout or "Aseprite export failed").strip()
        if request.export.aseprite == "required":
            raise RuntimeError(message)
        return None, message
    return target, None


def _write_manifest(
    staging: Path,
    request: PixelArtRequest,
    palette: list[tuple[int, int, int]],
    references: list[Path],
    candidate_scores: list[dict],
    stage_stats: dict,
    paths: dict[str, Path],
    backend_metadata: dict,
    semantic: dict,
    success: bool,
    promoted_files: dict[str, str] | None = None,
) -> dict:
    def manifest_path(path: Path) -> str:
        try:
            return path.relative_to(staging).as_posix()
        except ValueError:
            return str(path)

    files = {
        name: {"path": manifest_path(path), "sha256": sha256_file(path)}
        for name, path in paths.items()
        if path.exists()
    }
    manifest_model = Manifest(
        success=success,
        request=request.model_dump(mode="json"),
        prompt_plan=PromptCompiler().compile(request).model_dump(mode="json"),
        palette=describe_palette(palette),
        references=[str(path) for path in references],
        candidate_scores=candidate_scores,
        frame_manifest=stage_stats.get("frames", []),
        stage_stats=stage_stats,
        files=files,
        backend=backend_metadata,
        semantic_review=semantic,
        promoted_files=promoted_files or {},
    )
    manifest = manifest_model.model_dump(mode="json")
    if request.export.save_manifest:
        write_json(staging / "manifest.json", manifest)
    return manifest


def compile_image(
    source: Image.Image | str | Path,
    request: PixelArtRequest,
    candidate_scores: list[dict] | None = None,
    backend_metadata: dict | None = None,
) -> CompileResult:
    request, context = resolve_request(request)
    output_dir = resolve_output_dir(request, context).resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not request.export.overwrite:
        raise FileExistsError(f"output directory already exists: {output_dir}")
    request = PixelArtRequest.model_validate(
        request.model_copy(
            update={"export": request.export.model_copy(update={"output_dir": output_dir})}
        ).model_dump(mode="python")
    )
    preflight_promotion(request, context)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / f".{output_dir.name}.tmp-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        intermediate = staging / "intermediate" if request.export.save_intermediate else None
        if intermediate:
            intermediate.mkdir()
        image = (
            source.convert("RGBA")
            if isinstance(source, Image.Image)
            else Image.open(source).convert("RGBA")
        )
        if intermediate:
            image.save(intermediate / "00_source.png")

        reference_paths = select_references(request, context)
        reference_artifacts = write_reference_artifacts(
            reference_paths,
            staging / "references",
        )
        source_frames = (
            split_source_frames(image, request) if request.asset_type == "animation" else [image]
        )
        reduced_frames: list[Image.Image] = []
        frame_stage_stats: list[dict] = []
        for index, frame in enumerate(source_frames):
            reduced, stats = _reduce_frame(frame, request, index, intermediate)
            reduced_frames.append(reduced)
            frame_stage_stats.append(stats)
        palette = _choose_palette(reduced_frames, request, reference_paths, context)

        cleaned_frames: list[Image.Image] = []
        cleanup_stats: list[dict] = []
        for index, frame in enumerate(reduced_frames):
            cleaned, stats = _quantize_frame(
                frame,
                palette,
                request,
                index,
                intermediate,
                context,
            )
            cleaned_frames.append(cleaned)
            cleanup_stats.append(stats)

        grids = [image_to_grid(frame, palette) for frame in cleaned_frames]
        apply_patches(grids, request, palette)
        grid_path = staging / "grid.json"
        write_grid(grid_path, grids, palette, request)
        final_image = render_grid_file(grid_path)
        paths = export_images(
            final_image,
            palette,
            staging,
            request.export.preview_scale,
        )
        paths["grid"] = grid_path
        paths.update(reference_artifacts)

        validation = validate_image(paths["final"], request, paths["preview"])
        validation_path = staging / "validation_report.json"
        write_json(validation_path, validation.to_dict())
        paths["validation_report"] = validation_path
        if candidate_scores:
            candidate_path = staging / "candidate_scores.json"
            write_json(candidate_path, candidate_scores)
            paths["candidate_scores"] = candidate_path

        aseprite_path, aseprite_warning = _export_aseprite(staging, request)
        if aseprite_path:
            paths["aseprite"] = aseprite_path
        frame_manifest = animation_metrics(cleaned_frames)
        stage_stats = {
            "frames": frame_manifest,
            "frame_processing": frame_stage_stats,
            "cleanup": cleanup_stats,
            "aseprite_warning": aseprite_warning,
        }
        semantic = review(final_image, request, validation)
        backend = backend_metadata or {"name": "offline", "network_used": False}
        manifest = _write_manifest(
            staging,
            request,
            palette,
            reference_paths,
            candidate_scores or [],
            stage_stats,
            paths,
            backend,
            semantic,
            validation.success,
        )
        _safe_publish(staging, output_dir, request.export.overwrite)

        promoted: dict[str, str] = {}
        if validation.success and request.export.promote:
            promoted = promote_outputs(output_dir, request, context)
            manifest["promoted_files"] = promoted
            write_json(output_dir / "manifest.json", manifest)
            promoted_manifest = promoted.get("manifest")
            if promoted_manifest:
                write_json(Path(promoted_manifest), manifest)
        with Image.open(output_dir / "final.png") as loaded:
            delivered = loaded.convert("RGBA")
        return CompileResult(
            validation.success,
            delivered,
            palette,
            output_dir,
            manifest,
            validation,
        )
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def prepare_codex_handoff(request: PixelArtRequest) -> Path:
    request, context = resolve_request(request)
    output_dir = resolve_output_dir(request, context).resolve()
    handoff_dir = output_dir.with_name(f"{output_dir.name}_imagegen_handoff")
    if handoff_dir.exists() and any(handoff_dir.iterdir()) and not request.export.overwrite:
        raise FileExistsError(f"handoff directory already exists: {handoff_dir}")
    handoff_dir.mkdir(parents=True, exist_ok=True)
    references = select_references(request, context)
    artifacts = write_reference_artifacts(references, handoff_dir / "references")
    payload = {
        "schema_version": 1,
        "provider": "codex_imagegen",
        "asset_id": request.asset_id,
        "prompt": PromptCompiler().compile(request).model_dump(mode="json"),
        "reference_paths": [str(path) for path in references],
        "contact_sheet": str(artifacts.get("contact_sheet", "")),
        "next_step": (
            "Use Codex ImageGen with these references, save the selected precursor locally, "
            "then run pixel-art compile PRECURSOR --config REQUEST."
        ),
    }
    handoff = handoff_dir / "imagegen_handoff.json"
    write_json(handoff, payload)
    return handoff


def generate_image(request: PixelArtRequest) -> CompileResult:
    if not request.generation.allow_image_generation:
        raise BackendConfigurationError(
            "generation is disabled; set generation.allow_image_generation=true"
        )
    if request.generation.provider == "codex_imagegen":
        handoff = prepare_codex_handoff(request)
        raise BackendConfigurationError(
            f"Codex ImageGen handoff prepared at {handoff}; compile the returned precursor"
        )
    if request.generation.provider != "openai":
        raise BackendConfigurationError(
            "generate requires generation.provider='openai' or 'codex_imagegen'"
        )
    resolved, context = resolve_request(request)
    output_dir = resolve_output_dir(resolved, context).resolve()
    if output_dir.exists() and any(output_dir.iterdir()) and not resolved.export.overwrite:
        raise FileExistsError(f"output directory already exists: {output_dir}")
    references = select_references(resolved, context)
    from .openai_image_backend import OpenAIImageBackend

    backend = OpenAIImageBackend(
        resolved.generation.model,
        resolved.generation.quality,
        None,
    )
    plan = PromptCompiler().compile(resolved)
    candidates = backend.generate(
        plan.generation_prompt,
        resolved.generation.variants,
        resolved.generation.seed,
        references,
    )
    selected, scores = select_candidate(candidates, resolved)
    return compile_image(
        selected,
        resolved,
        scores,
        {
            "name": "openai",
            "network_used": True,
            "model": resolved.generation.model,
            "quality": resolved.generation.quality,
            "records": backend.records,
        },
    )
