from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import sys
from pathlib import Path

from PIL import Image

from .project import PROJECT_CONFIG_VERSION, find_project_root, load_yaml


def _aseprite() -> Path | None:
    candidates = [
        shutil.which("aseprite"),
        r"C:\Program Files\Aseprite\Aseprite.exe",
        r"C:\Program Files (x86)\Steam\steamapps\common\Aseprite\Aseprite.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def run_doctor(project_root: Path | None = None) -> tuple[bool, dict]:
    package_path = Path(__file__).resolve().parent
    skill_root = package_path.parent
    command = shutil.which("pixel-art")
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    check("skill_source", (skill_root / "SKILL.md").is_file(), str(skill_root))
    check("package_origin", skill_root in package_path.parents, str(package_path))
    check("global_cli", command is not None, command or "not found")
    try:
        dist = importlib.metadata.distribution("native-pixel-art")
        direct_url_text = dist.read_text("direct_url.json")
        direct_url = json.loads(direct_url_text) if direct_url_text else {}
        origin = str(direct_url.get("url", ""))
        canonical = skill_root.as_uri().lower().rstrip("/")
        check("distribution_source", origin.lower().rstrip("/") == canonical, origin or "unknown")
        version = dist.version
    except (importlib.metadata.PackageNotFoundError, json.JSONDecodeError, ValueError) as exc:
        check("distribution_source", False, str(exc))
        version = "not installed"
    check("python", sys.version_info >= (3, 11), sys.version.split()[0])
    for dependency in ("Pillow", "numpy", "pydantic", "typer", "PyYAML"):
        try:
            check(f"dependency:{dependency}", True, importlib.metadata.version(dependency))
        except importlib.metadata.PackageNotFoundError:
            check(f"dependency:{dependency}", False, "not installed")
    try:
        check("dependency:openai", True, importlib.metadata.version("openai"), required=False)
    except importlib.metadata.PackageNotFoundError:
        check(
            "dependency:openai",
            False,
            "not installed; only required for provider=openai",
            required=False,
        )
    aseprite = _aseprite()
    check(
        "aseprite", aseprite is not None, str(aseprite) if aseprite else "not found", required=False
    )
    check(
        "openai_api_key",
        bool(os.environ.get("OPENAI_API_KEY")),
        "configured" if os.environ.get("OPENAI_API_KEY") else "not set",
        required=False,
    )

    root = project_root.resolve() if project_root else find_project_root()
    if root:
        config_path = root / "tools" / "pixel_art" / "project.yaml"
        try:
            config = load_yaml(config_path)
            check(
                "project_config",
                config.get("schema_version") == PROJECT_CONFIG_VERSION,
                str(config_path),
            )
            profiles = config.get("profiles", {})
            profile_errors: list[str] = []
            if not isinstance(profiles, dict) or not profiles:
                profile_errors.append("profiles must be a non-empty object")
            else:
                for name, relative in profiles.items():
                    profile_path = (config_path.parent / str(relative)).resolve()
                    try:
                        profile = load_yaml(profile_path)
                        if profile.get("schema_version") != PROJECT_CONFIG_VERSION:
                            profile_errors.append(f"{name}: unsupported schema version")
                        if profile.get("name") != name:
                            profile_errors.append(f"{name}: profile name mismatch")
                    except (OSError, ValueError) as exc:
                        profile_errors.append(f"{name}: {exc}")
            check(
                "style_profiles",
                not profile_errors,
                "valid" if not profile_errors else "; ".join(profile_errors),
            )

            catalog_path = (
                config_path.parent / config.get("reference_catalog", "reference_catalog.yaml")
            ).resolve()
            catalog_errors: list[str] = []
            try:
                catalog = load_yaml(catalog_path)
                if catalog.get("schema_version") != PROJECT_CONFIG_VERSION:
                    catalog_errors.append("unsupported catalog schema version")
                references = catalog.get("references", [])
                if not isinstance(references, list) or not references:
                    catalog_errors.append("references must be a non-empty list")
                else:
                    for item in references:
                        if not isinstance(item, dict) or "path" not in item:
                            catalog_errors.append("catalog item is missing path")
                            continue
                        source = (root / str(item["path"])).resolve()
                        if not source.is_file():
                            catalog_errors.append(f"missing: {item['path']}")
                            continue
                        with Image.open(source) as image:
                            expected = (item.get("width"), item.get("height"))
                            if expected != image.size:
                                catalog_errors.append(
                                    f"size mismatch: {item['path']} {expected} != {image.size}"
                                )
            except (OSError, ValueError) as exc:
                catalog_errors.append(str(exc))
            check(
                "reference_catalog",
                not catalog_errors,
                f"{catalog_path} ({len(catalog.get('references', []))} references)"
                if not catalog_errors
                else "; ".join(catalog_errors),
            )
        except (OSError, ValueError) as exc:
            check("project_config", False, str(exc))
    else:
        check("project_config", True, "no project detected", required=False)
    success = all(item["ok"] for item in checks if item["required"])
    return success, {
        "success": success,
        "skill_root": str(skill_root),
        "package_version": version,
        "checks": checks,
    }


def find_aseprite() -> Path | None:
    return _aseprite()
