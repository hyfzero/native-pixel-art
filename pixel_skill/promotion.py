from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .config import PixelArtRequest
from .project import ProjectContext, resolve_project_path


def _destination(
    request: PixelArtRequest,
    context: ProjectContext | None,
) -> Path:
    if request.export.promote_to is None:
        raise ValueError("promotion destination is missing")
    destination = resolve_project_path(request.export.promote_to, context)
    if context:
        roots = [
            resolve_project_path(Path(value), context)
            for value in context.config.get("promotion_roots", [])
        ]
        if roots and not any(
            destination == root or destination.is_relative_to(root) for root in roots
        ):
            raise ValueError(
                f"promotion destination {destination} is outside configured promotion roots"
            )
    return destination


def _targets(
    output_dir: Path,
    destination: Path,
    request: PixelArtRequest,
) -> dict[str, tuple[Path, Path]]:
    mapping = {
        "png": (output_dir / "final.png", destination / f"{request.asset_id}.png"),
        "grid": (
            output_dir / "grid.json",
            destination / f"{request.asset_id}.grid.json",
        ),
        "manifest": (
            output_dir / "manifest.json",
            destination / f"{request.asset_id}.pixel-art.json",
        ),
    }
    if (output_dir / f"{request.asset_id}.aseprite").exists():
        mapping["aseprite"] = (
            output_dir / f"{request.asset_id}.aseprite",
            destination / f"{request.asset_id}.aseprite",
        )
    return mapping


def preflight_promotion(
    request: PixelArtRequest,
    context: ProjectContext | None,
) -> None:
    if not request.export.promote:
        return
    destination = _destination(request, context)
    expected = [
        destination / f"{request.asset_id}.png",
        destination / f"{request.asset_id}.grid.json",
        destination / f"{request.asset_id}.pixel-art.json",
    ]
    existing = [path for path in expected if path.exists()]
    if existing and not request.export.overwrite:
        raise FileExistsError(f"promotion target already exists: {existing[0]}")


def promote_outputs(
    output_dir: Path,
    request: PixelArtRequest,
    context: ProjectContext | None,
) -> dict[str, str]:
    if not request.export.promote:
        return {}
    destination = _destination(request, context)
    destination.mkdir(parents=True, exist_ok=True)
    mapping = _targets(output_dir, destination, request)
    missing = [source for source, _ in mapping.values() if not source.is_file()]
    if missing:
        raise FileNotFoundError(f"promotion source is missing: {missing[0]}")
    existing = [target for _, target in mapping.values() if target.exists()]
    if existing and not request.export.overwrite:
        raise FileExistsError(f"promotion target already exists: {existing[0]}")

    token = uuid.uuid4().hex
    staged: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    try:
        for source, target in mapping.values():
            temp = target.with_name(f".{target.name}.tmp-{token}")
            shutil.copy2(source, temp)
            staged.append((temp, target))
        for _, target in staged:
            if target.exists():
                backup = target.with_name(f".{target.name}.backup-{token}")
                target.replace(backup)
                backups.append((backup, target))
        for temp, target in staged:
            temp.replace(target)
            committed.append(target)
    except Exception:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
        for target in committed:
            target.unlink(missing_ok=True)
        for backup, target in backups:
            if backup.exists():
                backup.replace(target)
        raise
    for backup, _ in backups:
        backup.unlink(missing_ok=True)
    return {name: str(target) for name, (_, target) in mapping.items()}
