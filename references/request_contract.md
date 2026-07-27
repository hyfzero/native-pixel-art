# PixelArtRequest contract

Requests are YAML or JSON with `schema_version: 2`.

## Identity and geometry

- `asset_id`: stable snake_case identifier.
- `description`: subject, pose, orientation, and essential semantic features.
- `asset_type`: `static`, `tile`, or `animation`.
- `style_profile`: project profile ID or `generic`.
- `project_root`: repository root containing `tools/pixel_art/project.yaml`.
- Static/tile: `width`, `height`.
- Animation: `frame_width`, `frame_height`, `frame_count`, `columns`, `rows`, action ranges, FPS, and anchor/baseline tolerance.

## References and generation

- `references.mode`: `auto`, `explicit`, or `none`.
- `references.paths`: project-relative or absolute local PNG paths.
- `references.category`: character, npc, enemy, boss, item, tile, effect, ui, or any.
- `generation.provider`: `offline`, `codex_imagegen`, or `openai`.
- `generation.variants`: 1–6, normally 3.
- `generation.allow_image_generation`: explicit opt-in.
- Headless OpenAI defaults to `gpt-image-2`; a seed is rejected because support is not claimed.

## Palette and alpha

- `palette.mode`: `profile`, `fixed`, `adaptive`, or `semantic`.
- `palette.colors`: required legal RGB values for fixed mode.
- `palette.color_count`: 1–256 visible colors.
- `palette.count_rule`: `exact` or `maximum`.
- `palette.source`: request, references, source, or profile.
- `alpha.mode`: `binary` or `opaque`.
- Transparency does not count as a visible color by default.

## Output and promotion

- `export.output_dir`: staging result directory. Project default is `.godot/pixel_art_work/<asset_id>`.
- `export.overwrite`: required to replace an existing non-empty result or promotion target.
- `export.promote`: false by default; true only for explicit formal export.
- `export.promote_to`: project-relative asset directory.
- `export.aseprite`: off, auto, or required.

Promotion copies `<asset_id>.png`, `<asset_id>.grid.json`, the manifest, and optional Aseprite source only after all hard validations pass.

## Pixel patches

Patches are frame-local `set_pixel` or `fill_rect` operations using a legal palette color or transparency. They are for eyes, silhouette breaks, and anchor corrections. Keep patches bounded and semantically justified; never use them as color-count filler.
