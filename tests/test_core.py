from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from pixel_skill.config import PixelArtRequest, write_schemas
from pixel_skill.grid import render_grid_file
from pixel_skill.image_backend import (
    BackendConfigurationError,
    UnsupportedBackendOptionError,
)
from pixel_skill.openai_image_backend import OpenAIImageBackend
from pixel_skill.pipeline import compile_image, generate_image
from pixel_skill.validator import validate_image

DUOTONE = ["#000000", "#FEFEFE"]
ROOM_PALETTE = [
    "#1A1110",
    "#39231B",
    "#5B3626",
    "#7B4B31",
    "#9D6540",
    "#C48658",
    "#E3AE73",
    "#F2D09A",
    "#5A463A",
    "#806A58",
    "#B09A7C",
    "#E8D8B5",
]


def request(output: Path, **updates) -> PixelArtRequest:
    data = {
        "asset_id": "test_asset",
        "description": "test sprite",
        "width": 16,
        "height": 16,
        "references": {"mode": "none", "minimum": 0, "maximum": 0},
        "generation": {"provider": "offline"},
        "cleanup": {"remove_isolated_pixels": False},
        "export": {
            "output_dir": output,
            "preview_scale": 4,
            "aseprite": "off",
        },
    }
    data.update(updates)
    return PixelArtRequest.model_validate(data)


def visible_colors(image: Image.Image) -> set[tuple[int, int, int]]:
    array = np.asarray(image.convert("RGBA"))
    return {tuple(map(int, color)) for color in array[..., :3][array[..., 3] > 0]}


def duotone_source(size: tuple[int, int] = (96, 96)) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(20, 70), (26, 28), (42, 12), (48, 30), (65, 18), (76, 36), (72, 78)], fill="#000000"
    )
    draw.rectangle((37, 38, 56, 54), fill="#FEFEFE")
    draw.rectangle((45, 42, 50, 48), fill="#000000")
    return image


def room_source() -> Image.Image:
    image = Image.new("RGBA", (144, 144), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(ROOM_PALETTE):
        x = 18 + (index % 4) * 27
        y = 18 + (index // 4) * 34
        draw.rectangle((x, y, x + 25, y + 31), fill=color)
    return image


def animation_source() -> Image.Image:
    sheet = Image.new("RGBA", (128, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for index in range(4):
        x = index * 32
        draw.rectangle((x + 10, 8, x + 21, 27), fill="#000000")
        draw.rectangle((x + 13, 11, x + 18, 16), fill="#FEFEFE")
    return sheet


def test_16x16_duotone_exact_and_grid_roundtrip(tmp_path: Path):
    req = request(
        tmp_path / "goblin",
        palette={
            "mode": "fixed",
            "colors": DUOTONE,
            "color_count": 2,
            "count_rule": "exact",
        },
    )
    result = compile_image(duotone_source(), req)
    assert result.success, result.validation.to_dict()
    assert result.image.size == (16, 16)
    assert visible_colors(result.image) == {(0, 0, 0), (254, 254, 254)}
    assert render_grid_file(result.output_dir / "grid.json").tobytes() == result.image.tobytes()


def test_varying_chroma_border_is_removed_before_compilation(tmp_path: Path):
    width = height = 128
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    pixels[..., 1] = np.arange(height, dtype=np.uint8)[:, None] % 25 + 225
    pixels[..., 3] = 255
    source = Image.fromarray(pixels, "RGBA")
    draw = ImageDraw.Draw(source)
    draw.rectangle((42, 24, 85, 110), fill="#000000")
    draw.rectangle((54, 38, 73, 56), fill="#FFFFFF")
    req = request(
        tmp_path / "chroma",
        palette={
            "mode": "fixed",
            "colors": ["#000000", "#FFFFFF"],
            "color_count": 2,
            "count_rule": "exact",
        },
    )
    result = compile_image(source, req)
    assert result.success, result.validation.to_dict()
    assert visible_colors(result.image) == {(0, 0, 0), (255, 255, 255)}


def test_48x48_room_exact_twelve_colors(tmp_path: Path):
    req = request(
        tmp_path / "room_npc",
        width=48,
        height=48,
        palette={
            "mode": "fixed",
            "colors": ROOM_PALETTE,
            "color_count": 12,
            "count_rule": "exact",
        },
    )
    result = compile_image(room_source(), req)
    assert result.success, result.validation.to_dict()
    assert result.image.size == (48, 48)
    assert len(visible_colors(result.image)) == 12


def test_adaptive_exact_reference_palette_uses_meaningful_source_colors(
    tmp_path: Path,
):
    reference = tmp_path / "room_reference.png"
    reference_source = room_source()
    shifted = np.asarray(reference_source).copy()
    visible = shifted[..., 3] > 0
    shifted[..., :3][visible] = np.clip(
        shifted[..., :3][visible].astype(np.int16) + np.array([8, -4, 5]),
        0,
        255,
    )
    Image.fromarray(shifted.astype(np.uint8), "RGBA").save(reference)
    req = request(
        tmp_path / "adaptive_room",
        width=48,
        height=48,
        palette={
            "mode": "adaptive",
            "colors": [],
            "color_count": 12,
            "count_rule": "exact",
            "source": "references",
        },
        references={
            "mode": "explicit",
            "paths": [reference],
            "minimum": 1,
            "maximum": 1,
        },
    )
    result = compile_image(room_source(), req)
    assert result.success, result.validation.to_dict()
    assert len(visible_colors(result.image)) == 12


def test_four_frame_animation_is_128x32_and_stable(tmp_path: Path):
    req = request(
        tmp_path / "walk",
        asset_type="animation",
        palette={
            "mode": "fixed",
            "colors": DUOTONE,
            "color_count": 2,
            "count_rule": "exact",
        },
        animation={
            "frame_width": 32,
            "frame_height": 32,
            "frame_count": 4,
            "columns": 4,
            "rows": 1,
            "baseline_tolerance": 1,
            "anchor_tolerance": 1,
            "actions": [{"name": "walk", "start": 0, "count": 4, "fps": 8}],
        },
    )
    result = compile_image(animation_source(), req)
    assert result.success, result.validation.to_dict()
    assert result.image.size == (128, 32)
    assert len(result.validation.metrics["frames"]) == 4


@pytest.mark.parametrize(
    ("mutator", "expected_code"),
    [
        (lambda a: np.pad(a, ((0, 0), (0, 1), (0, 0))), "wrong_dimensions"),
        (lambda a: _set_pixel(a, (0, 0), (255, 0, 255, 255)), "palette_violation"),
        (lambda a: _set_pixel(a, (0, 0), (0, 0, 0, 128)), "non_binary_alpha"),
        (lambda a: _set_pixel(a, (0, 0), (255, 0, 255, 0)), "transparent_rgb_nonzero"),
    ],
)
def test_validator_rejects_corrupt_png(
    tmp_path: Path,
    mutator,
    expected_code: str,
):
    req = request(
        tmp_path / "unused",
        palette={
            "mode": "fixed",
            "colors": DUOTONE,
            "color_count": 2,
            "count_rule": "maximum",
        },
    )
    array = np.asarray(Image.new("RGBA", (16, 16), (0, 0, 0, 0))).copy()
    array[4:12, 4:12] = (0, 0, 0, 255)
    corrupted = mutator(array)
    path = tmp_path / f"{expected_code}.png"
    Image.fromarray(corrupted.astype(np.uint8), "RGBA").save(path)
    report = validate_image(path, req)
    assert not report.success
    assert expected_code in {failure["code"] for failure in report.hard_failures}


def _set_pixel(
    array: np.ndarray, xy: tuple[int, int], value: tuple[int, int, int, int]
) -> np.ndarray:
    result = array.copy()
    result[xy[1], xy[0]] = value
    return result


def test_validator_rejects_empty_animation_frame(tmp_path: Path):
    req = request(
        tmp_path / "unused",
        asset_type="animation",
        palette={"mode": "fixed", "colors": DUOTONE, "color_count": 2},
        animation={
            "frame_width": 32,
            "frame_height": 32,
            "frame_count": 4,
            "columns": 4,
            "rows": 1,
        },
    )
    source = animation_source()
    source.paste((0, 0, 0, 0), (96, 0, 128, 32))
    path = tmp_path / "missing_frame.png"
    source.save(path)
    report = validate_image(path, req)
    assert "empty_animation_frame" in {failure["code"] for failure in report.hard_failures}


def test_validator_rejects_modified_preview(tmp_path: Path):
    req = request(
        tmp_path / "preview",
        palette={"mode": "fixed", "colors": DUOTONE, "color_count": 2},
    )
    result = compile_image(duotone_source(), req)
    preview_path = result.output_dir / "preview_4x.png"
    preview = Image.open(preview_path).convert("RGBA")
    preview.putpixel((0, 0), (255, 0, 0, 255))
    preview.save(preview_path)
    report = validate_image(result.output_dir / "final.png", req, preview_path)
    assert "preview_not_nearest_neighbor" in {failure["code"] for failure in report.hard_failures}


def test_duplicate_output_is_refused(tmp_path: Path):
    req = request(
        tmp_path / "duplicate",
        palette={"mode": "fixed", "colors": DUOTONE, "color_count": 2},
    )
    compile_image(duotone_source(), req)
    with pytest.raises(FileExistsError):
        compile_image(duotone_source(), req)


def test_interruption_removes_only_staging(tmp_path: Path, monkeypatch):
    import pixel_skill.pipeline as pipeline

    output = tmp_path / "interrupted"
    req = request(output)

    def fail(*args, **kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(pipeline, "_reduce_frame", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        compile_image(duotone_source(), req)
    assert not output.exists()
    assert not list(tmp_path.glob(".interrupted.tmp-*"))


def test_promotion_only_after_validation(tmp_path: Path):
    project = tmp_path / "project"
    (project / "tools" / "pixel_art").mkdir(parents=True)
    (project / "assets" / "game_world").mkdir(parents=True)
    (project / "tools" / "pixel_art" / "project.yaml").write_text(
        "schema_version: 1\n"
        "work_dir: .work\n"
        "reference_catalog: reference_catalog.yaml\n"
        "profiles: {}\n"
        "promotion_roots: [assets/game_world]\n",
        encoding="utf-8",
    )
    req = request(
        project / ".work" / "promoted",
        project_root=project,
        asset_id="promoted",
        palette={"mode": "fixed", "colors": DUOTONE, "color_count": 2},
        export={
            "output_dir": project / ".work" / "promoted",
            "preview_scale": 4,
            "aseprite": "off",
            "promote": True,
            "promote_to": "assets/game_world/test",
        },
    )
    result = compile_image(duotone_source(), req)
    assert result.success
    assert (project / "assets" / "game_world" / "test" / "promoted.png").exists()


def test_promotion_outside_allowed_roots_is_refused(tmp_path: Path):
    project = tmp_path / "project"
    config = project / "tools" / "pixel_art"
    config.mkdir(parents=True)
    (config / "project.yaml").write_text(
        "schema_version: 1\n"
        "work_dir: .work\n"
        "reference_catalog: reference_catalog.yaml\n"
        "profiles: {}\n"
        "promotion_roots: [assets]\n",
        encoding="utf-8",
    )
    req = request(
        project / ".work" / "bad",
        project_root=project,
        export={
            "output_dir": project / ".work" / "bad",
            "aseprite": "off",
            "promote": True,
            "promote_to": "../outside",
        },
    )
    with pytest.raises(ValueError, match="outside configured"):
        compile_image(duotone_source(), req)


def test_schema_and_invalid_requests(tmp_path: Path):
    write_schemas(tmp_path)
    assert json.loads((tmp_path / "request.schema.json").read_text())["title"] == "PixelArtRequest"
    with pytest.raises(ValidationError):
        PixelArtRequest(asset_id="Not Valid")
    with pytest.raises(ValidationError):
        PixelArtRequest(
            palette={
                "mode": "fixed",
                "colors": ["#000000"],
                "color_count": 2,
                "count_rule": "exact",
            }
        )


class FakeResponse:
    def __init__(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode()
        self.data = [type("Datum", (), {"b64_json": encoded})()]

    def model_dump(self, mode="json"):
        return {"data": [{"b64_json": self.data[0].b64_json}]}


class FakeImages:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        return FakeResponse()

    def edit(self, **kwargs):
        self.calls.append(("edit", kwargs))
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.images = FakeImages()


def test_openai_multiple_references_use_edit(tmp_path: Path):
    references = []
    for index in range(2):
        path = tmp_path / f"ref{index}.png"
        Image.new("RGB", (8, 8), (index * 20, 0, 0)).save(path)
        references.append(path)
    client = FakeClient()
    backend = OpenAIImageBackend(metadata_dir=tmp_path / "meta", client=client)
    images = backend.generate("test", 2, references=references)
    assert len(images) == 2
    assert all(operation == "edit" for operation, _ in client.images.calls)
    assert all(len(params["image"]) == 2 for _, params in client.images.calls)
    assert len(list((tmp_path / "meta").glob("openai_edit_*.json"))) == 2


def test_openai_seed_and_missing_key_are_explicit(monkeypatch):
    backend = OpenAIImageBackend(client=FakeClient())
    with pytest.raises(UnsupportedBackendOptionError):
        backend.generate("test", 1, seed=7)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(BackendConfigurationError, match="OPENAI_API_KEY"):
        OpenAIImageBackend()


def test_offline_generate_is_refused(tmp_path: Path):
    req = request(
        tmp_path / "offline",
        generation={"provider": "offline", "allow_image_generation": True},
    )
    with pytest.raises(BackendConfigurationError, match="requires"):
        generate_image(req)
