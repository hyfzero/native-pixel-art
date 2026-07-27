from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from pixel_skill.cli import app

runner = CliRunner()


def source(path: Path, size: tuple[int, int] = (32, 32)) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 6, size[0] - 9, size[1] - 7), fill="#000000")
    draw.rectangle((12, 10, size[0] - 13, size[1] - 11), fill="#FFFFFF")
    image.save(path)


def test_legacy_compile_and_validate_flags(tmp_path: Path):
    source_path = tmp_path / "source.png"
    source(source_path)
    output = tmp_path / "out"
    compiled = runner.invoke(
        app,
        [
            "compile",
            str(source_path),
            "--width",
            "16",
            "--height",
            "16",
            "--palette",
            "#000000,#FFFFFF",
            "--output",
            str(output),
        ],
    )
    assert compiled.exit_code == 0, compiled.output
    validated = runner.invoke(
        app,
        [
            "validate",
            "--input",
            str(output / "final.png"),
            "--width",
            "16",
            "--height",
            "16",
            "--max-colors",
            "2",
            "--palette",
            "#000000,#FFFFFF",
        ],
    )
    assert validated.exit_code == 0, validated.output


def test_legacy_analyze_style(tmp_path: Path):
    source_path = tmp_path / "source.png"
    source(source_path)
    output = tmp_path / "style.json"
    result = runner.invoke(
        app,
        [
            "analyze-style",
            "--input",
            str(source_path),
            "--name",
            "test_style",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["name"] == "test_style"


def test_legacy_compile_opaque_flattens_alpha(tmp_path: Path):
    source_path = tmp_path / "source.png"
    source(source_path)
    output = tmp_path / "opaque"
    result = runner.invoke(
        app,
        [
            "compile",
            str(source_path),
            "--opaque",
            "--palette",
            "#000000,#FFFFFF",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    alpha = np.asarray(Image.open(output / "final.png").convert("RGBA"))[..., 3]
    assert set(np.unique(alpha)) == {255}


def test_legacy_animate_source_flags(tmp_path: Path):
    sheet = tmp_path / "sheet.png"
    image = Image.new("RGBA", (128, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for index in range(4):
        x = index * 32
        draw.rectangle((x + 10, 8, x + 21, 27), fill="#000000")
        draw.rectangle((x + 13, 11, x + 18, 16), fill="#FFFFFF")
    image.save(sheet)
    output = tmp_path / "animation"
    result = runner.invoke(
        app,
        [
            "animate",
            "--source",
            str(sheet),
            "--width",
            "32",
            "--height",
            "32",
            "--frames",
            "4",
            "--palette",
            "#000000,#FFFFFF",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert Image.open(output / "final.png").size == (128, 32)


def test_validation_failure_exit_code(tmp_path: Path):
    image = tmp_path / "wrong.png"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(image)
    config = tmp_path / "request.json"
    config.write_text(
        json.dumps(
            {
                "asset_id": "wrong",
                "width": 8,
                "height": 8,
                "references": {"mode": "none", "minimum": 0, "maximum": 0},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["validate", str(image), "--config", str(config)])
    assert result.exit_code == 4
    assert "wrong_dimensions" in result.stdout


def test_compile_validation_failure_preserves_exit_four(tmp_path: Path):
    source_path = tmp_path / "one_color.png"
    Image.new("RGBA", (16, 16), (0, 0, 0, 255)).save(source_path)
    config = tmp_path / "exact_two.json"
    config.write_text(
        json.dumps(
            {
                "asset_id": "exact_two",
                "width": 16,
                "height": 16,
                "palette": {
                    "mode": "fixed",
                    "colors": ["#000000", "#FFFFFF"],
                    "color_count": 2,
                    "count_rule": "exact",
                },
                "alpha": {"mode": "opaque"},
                "references": {"mode": "none", "minimum": 0, "maximum": 0},
                "cleanup": {"remove_isolated_pixels": False},
                "export": {
                    "output_dir": str(tmp_path / "failed"),
                    "aseprite": "off",
                },
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["compile", str(source_path), "--config", str(config)],
    )
    assert result.exit_code == 4
    assert "wrong_color_count" in result.output


def test_generate_without_api_key_is_backend_exit_three(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "generate",
            "--prompt",
            "goblin",
            "--provider",
            "openai",
            "--output",
            str(tmp_path / "generated"),
        ],
    )
    assert result.exit_code == 3
    assert "OPENAI_API_KEY" in result.output


def test_command_surface_contains_new_and_compatible_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "generate",
        "compile",
        "animate",
        "validate",
        "analyze-style",
        "profile-project",
        "doctor",
    ):
        assert command in result.output
