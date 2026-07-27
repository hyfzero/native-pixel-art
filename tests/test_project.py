from __future__ import annotations

import json
from pathlib import Path

import yaml
from PIL import Image

from pixel_skill.config import PixelArtRequest
from pixel_skill.project import resolve_request
from pixel_skill.references import profile_project, select_references


def make_project(root: Path) -> None:
    config = root / "tools" / "pixel_art"
    profiles = config / "profiles"
    profiles.mkdir(parents=True)
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    (config / "project.yaml").write_text(
        "schema_version: 1\n"
        "work_dir: .godot/pixel_art_work\n"
        "reference_catalog: reference_catalog.yaml\n"
        "profiles:\n"
        "  test_profile: profiles/test.yaml\n",
        encoding="utf-8",
    )
    (profiles / "test.yaml").write_text(
        "schema_version: 1\n"
        "request_defaults:\n"
        "  palette:\n"
        "    mode: fixed\n"
        "    colors: ['#000000', '#FEFEFE']\n"
        "    color_count: 2\n"
        "    count_rule: exact\n"
        "  references:\n"
        "    mode: auto\n"
        "    minimum: 1\n"
        "    maximum: 3\n",
        encoding="utf-8",
    )


def test_profile_defaults_and_explicit_override(tmp_path: Path):
    make_project(tmp_path)
    request = PixelArtRequest(
        asset_id="profiled",
        style_profile="test_profile",
        project_root=tmp_path,
    )
    resolved, _ = resolve_request(request)
    assert resolved.palette.colors == ["#000000", "#FEFEFE"]
    overridden = PixelArtRequest(
        asset_id="profiled",
        style_profile="test_profile",
        project_root=tmp_path,
        palette={
            "mode": "fixed",
            "colors": ["#000000", "#FFFFFF"],
            "color_count": 2,
            "count_rule": "exact",
        },
    )
    resolved_override, _ = resolve_request(overridden)
    assert resolved_override.palette.colors == ["#000000", "#FFFFFF"]


def test_explicit_reference_selection(tmp_path: Path):
    make_project(tmp_path)
    reference = tmp_path / "reference.png"
    Image.new("RGBA", (16, 16), (0, 0, 0, 255)).save(reference)
    request = PixelArtRequest(
        asset_id="explicit",
        project_root=tmp_path,
        references={
            "mode": "explicit",
            "paths": ["reference.png"],
            "minimum": 1,
            "maximum": 1,
        },
    )
    resolved, context = resolve_request(request)
    assert select_references(resolved, context) == [reference.resolve()]


def test_profile_project_writes_catalog_and_stats(tmp_path: Path):
    game = tmp_path / "assets" / "game_world" / "character"
    room = tmp_path / "assets" / "room" / "items"
    game.mkdir(parents=True)
    room.mkdir(parents=True)
    Image.new("RGBA", (16, 16), (0, 0, 0, 255)).save(game / "hero.png")
    Image.new("RGBA", (32, 32), (10, 20, 30, 255)).save(room / "lamp.png")
    paths = profile_project(tmp_path)
    catalog = yaml.safe_load(paths["catalog"].read_text(encoding="utf-8"))
    stats = json.loads(paths["statistics"].read_text(encoding="utf-8"))
    assert len(catalog["references"]) == 2
    assert stats["profiles"]["game_world_duotone"]["asset_count"] == 1
    assert stats["profiles"]["room_color"]["asset_count"] == 1
