from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image, ImageDraw

from .config import PixelArtRequest
from .exporter import write_json
from .palette import rgb_to_hex
from .project import ProjectContext, resolve_project_path


def image_statistics(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGBA")
    rgba = np.asarray(image)
    visible = rgba[..., 3] > 0
    pixels = rgba[..., :3][visible]
    colors, counts = (
        np.unique(pixels, axis=0, return_counts=True)
        if len(pixels)
        else (np.empty((0, 3), dtype=np.uint8), np.empty(0, dtype=int))
    )
    order = np.argsort(-counts, kind="stable")
    alpha_values = sorted(int(value) for value in np.unique(rgba[..., 3]))
    return {
        "width": image.width,
        "height": image.height,
        "visible_colors": int(len(colors)),
        "dominant_colors": [rgb_to_hex(colors[index]) for index in order[:16]],
        "binary_alpha": all(value in (0, 255) for value in alpha_values),
        "has_transparency": bool(np.any(rgba[..., 3] == 0)),
        "coverage": round(float(visible.mean()), 6),
    }


def infer_category(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    if "boss" in parts:
        return "boss"
    if "enemy" in parts:
        return "enemy"
    if "npc" in parts:
        return "npc"
    if parts & {"character", "characters", "player"}:
        return "character"
    if parts & {"item", "items", "drop_item", "weapon"}:
        return "item"
    if parts & {"tile", "tiles", "tileset", "tilesets"}:
        return "tile"
    if parts & {"effect", "effects", "particles", "animation"}:
        return "effect"
    if "ui" in parts:
        return "ui"
    return "any"


def profile_project(project_root: Path, output_dir: Path | None = None) -> dict[str, Path]:
    root = project_root.resolve()
    target = (output_dir or root / "tools" / "pixel_art").resolve()
    assets = root / "assets"
    entries: list[dict[str, Any]] = []
    profile_stats: dict[str, list[dict[str, Any]]] = {"game_world_duotone": [], "room_color": []}
    for path in sorted(assets.rglob("*.png")):
        if path.name.endswith(".import"):
            continue
        relative = path.relative_to(root)
        if "game_world" in relative.parts:
            profile = "game_world_duotone"
        elif "room" in relative.parts:
            profile = "room_color"
        else:
            continue
        try:
            stats = image_statistics(path)
        except OSError:
            continue
        entry = {
            "path": relative.as_posix(),
            "profile": profile,
            "category": infer_category(relative),
            "width": stats["width"],
            "height": stats["height"],
            "purpose": "style_reference",
            "weight": 1.0,
            "visible_colors": stats["visible_colors"],
        }
        entries.append(entry)
        profile_stats[profile].append(stats)
    target.mkdir(parents=True, exist_ok=True)
    catalog_path = target / "reference_catalog.yaml"
    catalog_path.write_text(
        yaml.safe_dump(
            {"schema_version": 1, "references": entries}, sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )
    summary = {
        "schema_version": 1,
        "profiles": {
            name: {
                "asset_count": len(values),
                "dominant_colors": [
                    color
                    for color, _ in Counter(
                        color for stats in values for color in stats["dominant_colors"][:8]
                    ).most_common(24)
                ],
                "visible_color_range": [
                    min((stats["visible_colors"] for stats in values), default=0),
                    max((stats["visible_colors"] for stats in values), default=0),
                ],
            }
            for name, values in profile_stats.items()
        },
    }
    summary_path = target / "style_stats.json"
    write_json(summary_path, summary)
    return {"catalog": catalog_path, "statistics": summary_path}


def _load_catalog(context: ProjectContext) -> list[dict[str, Any]]:
    if not context.catalog_path.exists():
        return []
    data = yaml.safe_load(context.catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"invalid reference catalog: {context.catalog_path}")
    return list(data.get("references", []))


def select_references(request: PixelArtRequest, context: ProjectContext | None) -> list[Path]:
    if request.references.mode == "none":
        return []
    if request.references.mode == "auto" and request.style_profile == "generic":
        return []
    if request.references.mode == "explicit":
        paths = [resolve_project_path(path, context) for path in request.references.paths]
    else:
        if context is None:
            return []
        target_w, target_h = request.frame_size
        category = request.references.category
        candidates = []
        for entry in _load_catalog(context):
            if entry.get("profile") != request.style_profile:
                continue
            entry_category = entry.get("category", "any")
            category_bonus = (
                3.0
                if category != "any" and entry_category == category
                else 0.5
                if category == "any"
                else -2.0
            )
            width = max(1, int(entry.get("width", 1)))
            height = max(1, int(entry.get("height", 1)))
            size_distance = abs(math.log2(width / target_w)) + abs(math.log2(height / target_h))
            score = float(entry.get("weight", 1.0)) * 4.0 + category_bonus - size_distance
            candidates.append((score, str(entry.get("path"))))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        paths = [context.root / value for _, value in candidates[: request.references.maximum]]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"missing reference images: {[str(path) for path in missing]}")
    if len(paths) < request.references.minimum:
        raise ValueError(
            f"only {len(paths)} references selected; minimum is {request.references.minimum}"
        )
    return paths[: request.references.maximum]


def write_reference_artifacts(paths: list[Path], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = [{"path": str(path), **image_statistics(path)} for path in paths]
    stats_path = output_dir / "reference_stats.json"
    write_json(stats_path, {"references": stats})
    if not paths:
        return {"statistics": stats_path}
    thumb_size = 128
    columns = min(3, len(paths))
    rows = math.ceil(len(paths) / columns)
    sheet = Image.new("RGBA", (columns * thumb_size, rows * (thumb_size + 24)), (32, 32, 32, 255))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGBA")
        image.thumbnail((thumb_size - 8, thumb_size - 8), Image.Resampling.NEAREST)
        x = (index % columns) * thumb_size + (thumb_size - image.width) // 2
        y0 = (index // columns) * (thumb_size + 24)
        y = y0 + (thumb_size - image.height) // 2
        sheet.alpha_composite(image, (x, y))
        draw.text(
            ((index % columns) * thumb_size + 4, y0 + thumb_size + 4), path.name[:20], fill="white"
        )
    contact_path = output_dir / "reference_contact_sheet.png"
    sheet.save(contact_path, format="PNG", optimize=False)
    return {"statistics": stats_path, "contact_sheet": contact_path}
