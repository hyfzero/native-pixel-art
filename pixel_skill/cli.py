from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml
from PIL import Image
from pydantic import ValidationError

from .config import PixelArtRequest
from .doctor import run_doctor
from .downsample import nearest_preview
from .exporter import describe_palette, palette_strip, write_json
from .image_backend import ImageBackendError
from .palette import extract_palette, hex_to_rgb, load_palette
from .pipeline import compile_image, generate_image
from .project import resolve_request
from .references import image_statistics, profile_project
from .validator import validate_image

app = typer.Typer(
    help="Project-aware native pixel-art generation, compilation, and validation.",
    no_args_is_help=True,
)
palette_app = typer.Typer(help="Palette utilities.", no_args_is_help=True)
app.add_typer(palette_app, name="palette")


def _request(path: Path) -> PixelArtRequest:
    try:
        request = PixelArtRequest.from_file(path)
        resolved, _ = resolve_request(request)
        return resolved
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(2) from exc


def _asset_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized or not normalized[0].isalpha():
        normalized = f"asset_{normalized or 'pixel'}"
    return normalized


def _palette_values(value: str | None) -> list[str] | None:
    if not value:
        return None
    path = Path(value)
    builtin = Path(__file__).parents[1] / "palettes" / f"{value}.yaml"
    if path.exists():
        colors = load_palette(path)
    elif builtin.exists():
        colors = load_palette(builtin)
    else:
        colors = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not colors:
        raise ValueError("palette is empty")
    for color in colors:
        hex_to_rgb(color)
    return colors


def _output_details(
    output: Path | None,
    asset_id: str,
) -> tuple[Path | None, Path | None]:
    if output is None:
        return None, None
    if output.suffix.lower() == ".png":
        return output.parent / f"{output.stem}_pixel_art", output
    return output, None


def _direct_request(
    *,
    prompt: str,
    width: int,
    height: int,
    output: Path | None,
    max_colors: int,
    palette: str | None,
    background: str,
    background_color: str,
    outline: str,
    shading: int,
    dithering: str,
    style: str,
    candidates: int,
    seed: int | None,
    provider: str,
    asset_type: str = "static",
    frames: int = 1,
    columns: int | None = None,
    rows: int = 1,
    overwrite: bool = False,
    alpha_mode: str = "binary",
) -> tuple[PixelArtRequest, Path | None]:
    colors = _palette_values(palette)
    identifier = _asset_id(output.stem if output else "pixel_asset")
    output_dir, legacy_file = _output_details(output, identifier)
    palette_data = {
        "mode": "fixed" if colors else "adaptive",
        "colors": colors or [],
        "color_count": len(colors) if colors else max_colors,
        "count_rule": "maximum",
        "source": "source",
    }
    provider_value = "codex_imagegen" if provider in {"codex", "codex_imagegen"} else provider
    request = PixelArtRequest(
        asset_id=identifier,
        description=prompt,
        asset_type=asset_type,
        width=width,
        height=height,
        palette=palette_data,
        alpha={"mode": alpha_mode},
        background={"mode": background, "color": background_color},
        style={
            "profile": style,
            "outline": outline,
            "shading_levels": shading,
            "dithering": dithering,
        },
        references={"mode": "none", "minimum": 0, "maximum": 0},
        generation={
            "provider": provider_value,
            "variants": candidates,
            "seed": seed,
            "allow_image_generation": provider_value in {"openai", "codex_imagegen"},
        },
        animation={
            "frame_width": width,
            "frame_height": height,
            "frame_count": frames,
            "columns": columns or frames,
            "rows": rows,
        },
        export={"output_dir": output_dir, "overwrite": overwrite},
    )
    return request, legacy_file


def _preflight_legacy_file(legacy_file: Path | None, overwrite: bool) -> None:
    if legacy_file is not None and legacy_file.exists() and not overwrite:
        raise FileExistsError(f"output already exists: {legacy_file}")


def _apply_export_overrides(
    request: PixelArtRequest,
    output: Path | None,
    overwrite: bool,
    promote: bool,
    promote_to: Path | None,
) -> tuple[PixelArtRequest, Path | None]:
    output_dir, legacy_file = _output_details(output, request.asset_id)
    updates = request.export.model_dump(mode="python")
    if output_dir is not None:
        updates["output_dir"] = output_dir
    if overwrite:
        updates["overwrite"] = True
    if promote:
        updates["promote"] = True
    if promote_to is not None:
        updates["promote_to"] = promote_to
    data = request.model_dump(mode="python")
    data["export"] = updates
    return PixelArtRequest.model_validate(data), legacy_file


def _finish(result, legacy_file: Path | None = None) -> None:
    if not result.success:
        typer.echo(json.dumps(result.validation.to_dict(), indent=2), err=True)
        raise typer.Exit(4)
    if legacy_file is not None:
        if legacy_file.exists() and not result.manifest["request"]["export"]["overwrite"]:
            typer.echo(f"output already exists: {legacy_file}", err=True)
            raise typer.Exit(6)
        legacy_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(result.output_dir / "final.png", legacy_file)
        typer.echo(str(legacy_file))
    else:
        typer.echo(str(result.output_dir / "final.png"))


@app.command("generate")
def generate(
    config: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, readable=True),
    prompt: str = typer.Option("pixel art subject"),
    width: int = typer.Option(32, min=1, max=512),
    height: int = typer.Option(32, min=1, max=512),
    output: Optional[Path] = typer.Option(None),
    max_colors: int = typer.Option(8, min=1, max=256),
    palette: Optional[str] = typer.Option(None),
    background: str = typer.Option("transparent"),
    background_color: str = typer.Option("#000000"),
    outline: str = typer.Option("automatic"),
    shading: int = typer.Option(2, min=1, max=8),
    dithering: str = typer.Option("off"),
    symmetry: str = typer.Option("none", help="Compatibility option; included in the prompt."),
    style: str = typer.Option("clean_sprite"),
    candidates: int = typer.Option(3, min=1, max=6),
    seed: Optional[int] = typer.Option(None),
    provider: str = typer.Option("openai"),
    overwrite: bool = typer.Option(False),
    promote: bool = typer.Option(False),
    promote_to: Optional[Path] = typer.Option(None),
) -> None:
    """Generate precursor candidates, select one, then compile and independently validate it."""
    legacy_file = None
    try:
        if config:
            request = _request(config)
            request, legacy_file = _apply_export_overrides(
                request, output, overwrite, promote, promote_to
            )
        else:
            request, legacy_file = _direct_request(
                prompt=f"{prompt}. Symmetry requirement: {symmetry}.",
                width=width,
                height=height,
                output=output,
                max_colors=max_colors,
                palette=palette,
                background=background,
                background_color=background_color,
                outline=outline,
                shading=shading,
                dithering=dithering,
                style=style,
                candidates=candidates,
                seed=seed,
                provider=provider,
                overwrite=overwrite,
            )
        _preflight_legacy_file(legacy_file, request.export.overwrite)
        _finish(generate_image(request), legacy_file)
    except typer.Exit:
        raise
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(6) from exc
    except (ImageBackendError, RuntimeError) as exc:
        typer.echo(f"backend error: {exc}", err=True)
        raise typer.Exit(3) from exc
    except (ValidationError, ValueError, OSError) as exc:
        typer.echo(f"configuration error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command("compile")
def compile_command(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    config: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, readable=True),
    width: Optional[int] = typer.Option(None, min=1, max=512),
    height: Optional[int] = typer.Option(None, min=1, max=512),
    palette: Optional[str] = typer.Option(None),
    max_colors: int = typer.Option(8, min=1, max=256),
    transparent: Optional[bool] = typer.Option(None, "--transparent/--opaque"),
    output: Optional[Path] = typer.Option(None),
    overwrite: bool = typer.Option(False),
    promote: bool = typer.Option(False),
    promote_to: Optional[Path] = typer.Option(None),
) -> None:
    """Compile a local precursor without network access."""
    legacy_file = None
    try:
        if config:
            request = _request(config)
            request, legacy_file = _apply_export_overrides(
                request, output, overwrite, promote, promote_to
            )
            data = request.model_dump(mode="python")
            if width is not None:
                data["width"] = width
            if height is not None:
                data["height"] = height
            if transparent is not None:
                data["background"]["mode"] = "transparent" if transparent else "preserve"
                data["alpha"]["mode"] = "binary" if transparent else "opaque"
            colors = _palette_values(palette)
            if colors:
                data["palette"] = {
                    "mode": "fixed",
                    "colors": colors,
                    "color_count": len(colors),
                    "count_rule": "maximum",
                    "source": "request",
                }
            request = PixelArtRequest.model_validate(data)
        else:
            with Image.open(source) as image:
                source_width, source_height = image.size
            request, legacy_file = _direct_request(
                prompt=source.stem.replace("_", " "),
                width=width or source_width,
                height=height or source_height,
                output=output,
                max_colors=max_colors,
                palette=palette,
                background="transparent" if transparent is not False else "preserve",
                background_color="#000000",
                outline="automatic",
                shading=2,
                dithering="off",
                style="clean_sprite",
                candidates=1,
                seed=None,
                provider="offline",
                overwrite=overwrite,
                alpha_mode="opaque" if transparent is False else "binary",
            )
        _preflight_legacy_file(legacy_file, request.export.overwrite)
        _finish(compile_image(source, request), legacy_file)
    except typer.Exit:
        raise
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(6) from exc
    except (ValidationError, ValueError, OSError, RuntimeError) as exc:
        typer.echo(f"compile error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command("animate")
def animate_command(
    source: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, readable=True),
    config: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, readable=True),
    prompt: str = typer.Option("pixel art animation"),
    width: int = typer.Option(32, min=1, max=512),
    height: int = typer.Option(32, min=1, max=512),
    frames: int = typer.Option(4, min=1, max=64),
    columns: Optional[int] = typer.Option(None, min=1, max=64),
    rows: int = typer.Option(1, min=1, max=64),
    output: Optional[Path] = typer.Option(None),
    fps: int = typer.Option(8, min=1, max=60),
    type: str = typer.Option("walk", help="Compatibility animation action name."),
    palette: Optional[str] = typer.Option(None),
    max_colors: int = typer.Option(8, min=1, max=256),
    background: str = typer.Option("transparent"),
    seed: Optional[int] = typer.Option(None),
    provider: str = typer.Option("openai"),
    overwrite: bool = typer.Option(False),
) -> None:
    """Compile a fixed-grid source sheet or generate a precursor animation sheet."""
    legacy_file = None
    try:
        if config:
            request = _request(config)
            request, legacy_file = _apply_export_overrides(request, output, overwrite, False, None)
        else:
            request, legacy_file = _direct_request(
                prompt=prompt,
                width=width,
                height=height,
                output=output,
                max_colors=max_colors,
                palette=palette,
                background=background,
                background_color="#000000",
                outline="automatic",
                shading=2,
                dithering="off",
                style="clean_sprite",
                candidates=3,
                seed=seed,
                provider="offline" if source else provider,
                asset_type="animation",
                frames=frames,
                columns=columns,
                rows=rows,
                overwrite=overwrite,
            )
            data = request.model_dump(mode="python")
            data["animation"]["actions"] = [{"name": type, "start": 0, "count": frames, "fps": fps}]
            request = PixelArtRequest.model_validate(data)
        _preflight_legacy_file(legacy_file, request.export.overwrite)
        result = compile_image(source, request) if source else generate_image(request)
        _finish(result, legacy_file)
    except typer.Exit:
        raise
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(6) from exc
    except ImageBackendError as exc:
        typer.echo(f"backend error: {exc}", err=True)
        raise typer.Exit(3) from exc
    except (ValidationError, ValueError, OSError, RuntimeError) as exc:
        typer.echo(f"animation error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command("validate")
def validate_command(
    image: Optional[Path] = typer.Argument(None),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    config: Optional[Path] = typer.Option(None, exists=True, dir_okay=False, readable=True),
    width: Optional[int] = typer.Option(None, min=1, max=32768),
    height: Optional[int] = typer.Option(None, min=1, max=32768),
    max_colors: int = typer.Option(256, min=1, max=256),
    palette: Optional[str] = typer.Option(None),
    alpha_binary: bool = typer.Option(True, "--alpha-binary/--allow-partial-alpha"),
    report: Optional[Path] = typer.Option(None, "--report"),
    output: Optional[Path] = typer.Option(None),
) -> None:
    """Independently reload and validate an existing PNG."""
    target = input_path or image
    if target is None or not target.is_file():
        typer.echo("validation input PNG is required", err=True)
        raise typer.Exit(2)
    try:
        if config:
            request = _request(config)
        else:
            with Image.open(target) as loaded:
                actual_width, actual_height = loaded.size
            colors = _palette_values(palette)
            request = PixelArtRequest(
                width=width or actual_width,
                height=height or actual_height,
                palette={
                    "mode": "fixed" if colors else "adaptive",
                    "colors": colors or [],
                    "color_count": len(colors) if colors else max_colors,
                    "count_rule": "maximum",
                    "source": "source",
                },
                references={"mode": "none", "minimum": 0, "maximum": 0},
                cleanup={"binary_alpha": alpha_binary},
                export={"aseprite": "off"},
            )
        validation = validate_image(target, request)
        data = validation.to_dict()
        destination = report or output
        if destination:
            write_json(destination, data)
        typer.echo(json.dumps(data, indent=2))
        if not validation.success:
            raise typer.Exit(4)
    except typer.Exit:
        raise
    except (ValidationError, ValueError, OSError) as exc:
        typer.echo(f"validation error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command("analyze-style")
def analyze_style(
    input_path: Path = typer.Option(..., "--input", exists=True, readable=True),
    name: str = typer.Option("custom_style"),
    output: Path = typer.Option(...),
) -> None:
    """Analyze one image or a directory into a compact compatibility style profile."""
    paths = [input_path] if input_path.is_file() else sorted(input_path.rglob("*.png"))
    if not paths:
        typer.echo("no PNG files found", err=True)
        raise typer.Exit(2)
    stats = [{"path": str(path), **image_statistics(path)} for path in paths]
    payload = {
        "schema_version": 1,
        "name": name,
        "asset_count": len(stats),
        "assets": stats,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() in {".yaml", ".yml"}:
        output.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    else:
        write_json(output, payload)
    typer.echo(str(output))


@app.command("profile-project")
def profile_project_command(
    project_root: Path = typer.Option(Path.cwd(), exists=True, file_okay=False),
    output: Optional[Path] = typer.Option(None, file_okay=False),
) -> None:
    """Scan project assets and rebuild the deterministic reference catalog and style statistics."""
    try:
        paths = profile_project(project_root, output)
        typer.echo(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))
    except (OSError, ValueError) as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command("doctor")
def doctor_command(
    project_root: Optional[Path] = typer.Option(None, exists=True, file_okay=False),
) -> None:
    """Check canonical CLI origin, dependencies, Aseprite, API key, and project config."""
    success, report = run_doctor(project_root)
    typer.echo(json.dumps(report, indent=2))
    if not success:
        raise typer.Exit(5)


@palette_app.command("extract")
def palette_extract(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    colors: int = typer.Option(8, min=1, max=256),
    output: Optional[Path] = typer.Option(None, dir_okay=False),
) -> None:
    """Extract a deterministic perceptual palette from a local image."""
    values = extract_palette(Image.open(source), colors)
    payload = {"colors": describe_palette(values)}
    typer.echo(json.dumps(payload, indent=2))
    if output:
        if output.suffix.lower() == ".png":
            palette_strip(values).save(output)
        else:
            write_json(output, payload)


@app.command("preview")
def preview_command(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    scale: int = typer.Option(12, min=1, max=64),
    output: Optional[Path] = typer.Option(None, dir_okay=False),
) -> None:
    """Create an integer nearest-neighbor preview without introducing colors."""
    image = Image.open(source).convert("RGBA")
    target = output or source.with_name(f"{source.stem}_preview_{scale}x.png")
    nearest_preview(image, scale).save(target)
    typer.echo(str(target))


if __name__ == "__main__":
    app()
