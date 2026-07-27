from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import PixelArtRequest

PROJECT_CONFIG_VERSION = 1


@dataclass(frozen=True)
class ProjectContext:
    root: Path
    config_path: Path
    config: dict[str, Any]
    profile_path: Path | None
    profile: dict[str, Any]

    @property
    def work_dir(self) -> Path:
        return self.root / self.config.get("work_dir", ".godot/pixel_art_work")

    @property
    def catalog_path(self) -> Path:
        return self.config_path.parent / self.config.get(
            "reference_catalog", "reference_catalog.yaml"
        )


def find_project_root(start: str | Path | None = None) -> Path | None:
    current = Path(start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "project.godot").exists() or (
            candidate / "tools" / "pixel_art" / "project.yaml"
        ).exists():
            return candidate
    return None


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def load_project_context(
    request: PixelArtRequest, require_profile: bool = False
) -> ProjectContext | None:
    root = Path(request.project_root).resolve() if request.project_root else find_project_root()
    if root is None:
        if require_profile:
            raise ValueError("project root not found; set project_root")
        return None
    config_path = (
        (root / request.project_config).resolve()
        if request.project_config and not Path(request.project_config).is_absolute()
        else Path(request.project_config).resolve()
        if request.project_config
        else root / "tools" / "pixel_art" / "project.yaml"
    )
    if not config_path.exists():
        if require_profile:
            raise ValueError(f"project pixel-art config not found: {config_path}")
        return None
    config = load_yaml(config_path)
    if config.get("schema_version") != PROJECT_CONFIG_VERSION:
        raise ValueError(
            f"unsupported project pixel-art config version {config.get('schema_version')!r}; "
            f"expected {PROJECT_CONFIG_VERSION}"
        )
    profile_path = None
    profile: dict[str, Any] = {}
    profile_ref = config.get("profiles", {}).get(request.style_profile)
    if profile_ref:
        profile_path = (config_path.parent / profile_ref).resolve()
        profile = load_yaml(profile_path)
        if profile.get("schema_version") != PROJECT_CONFIG_VERSION:
            raise ValueError(f"unsupported style profile version in {profile_path}")
    elif require_profile or request.style_profile != "generic":
        raise ValueError(f"unknown style_profile {request.style_profile!r}")
    return ProjectContext(root, config_path, config, profile_path, profile)


def _deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def resolve_request(request: PixelArtRequest) -> tuple[PixelArtRequest, ProjectContext | None]:
    context = load_project_context(request, require_profile=request.style_profile != "generic")
    if context is None or not context.profile:
        return request, context
    profile_defaults = context.profile.get("request_defaults", {})
    if not isinstance(profile_defaults, dict):
        raise ValueError("style profile request_defaults must be an object")
    raw = request.model_dump(mode="python")
    explicit = request.model_fields_set
    merged = deepcopy(raw)
    for key, value in profile_defaults.items():
        if key not in explicit:
            merged[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(raw.get(key), dict):
            nested_explicit = (
                getattr(request, key).model_fields_set
                if hasattr(getattr(request, key), "model_fields_set")
                else set()
            )
            nested = deepcopy(raw[key])
            for nested_key, nested_value in value.items():
                if nested_key not in nested_explicit:
                    nested[nested_key] = deepcopy(nested_value)
            merged[key] = nested
    merged["project_root"] = context.root
    return PixelArtRequest.model_validate(merged), context


def resolve_output_dir(request: PixelArtRequest, context: ProjectContext | None) -> Path:
    if request.export.output_dir:
        path = Path(request.export.output_dir)
        return (
            path if path.is_absolute() else (context.root / path if context else Path.cwd() / path)
        )
    if context:
        return context.work_dir / request.asset_id
    return Path.cwd() / "pixel_art_work" / request.asset_id


def resolve_project_path(path: Path, context: ProjectContext | None) -> Path:
    if path.is_absolute():
        return path.resolve()
    return ((context.root if context else Path.cwd()) / path).resolve()
