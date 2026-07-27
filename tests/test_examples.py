from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pixel_skill.config import PixelArtRequest
from pixel_skill.pipeline import compile_image

ROOT = Path(__file__).parents[1]


def make_source(kind: str) -> Image.Image:
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if kind == "icon":
        draw.ellipse((24, 20, 104, 108), fill="white")
        draw.ellipse((50, 10, 112, 92), fill=(0, 0, 0, 0))
    elif kind == "character":
        draw.ellipse((40, 12, 88, 58), fill="#D99A65")
        draw.rectangle((32, 54, 96, 116), fill="#486B3C")
        draw.rectangle((26, 110, 58, 126), fill="#4A2B20")
        draw.rectangle((70, 110, 102, 126), fill="#4A2B20")
    else:
        draw.ellipse((18, 10, 110, 124), fill="#D99A65")
        draw.polygon([(20, 20), (104, 8), (122, 72), (84, 50)], fill="#3A2548")
        draw.ellipse((72, 52, 82, 62), fill="#111111")
    return image


def test_three_end_to_end_examples(tmp_path: Path):
    cases = [
        ("icon-16.json", "icon"),
        ("character-32.json", "character"),
        ("portrait-64.json", "portrait"),
    ]
    for filename, kind in cases:
        req = PixelArtRequest.from_json(ROOT / "examples" / filename)
        req = PixelArtRequest.model_validate(
            req.model_copy(
                update={"export": req.export.model_copy(update={"output_dir": tmp_path / kind})}
            ).model_dump()
        )
        result = compile_image(make_source(kind), req)
        assert result.success, result.validation.to_dict()
        assert (tmp_path / kind / "final.png").exists()
        assert (tmp_path / kind / "manifest.json").exists()
        assert (tmp_path / kind / "validation_report.json").exists()
