# Native Pixel Art

[English](README.md) | [简体中文](README.zh-CN.md)

A deterministic, project-aware pixel-art compiler and Codex Skill for producing game-ready PNG assets with exact dimensions, controlled palettes, binary alpha, reproducible grids, and independent validation.

Image generation is treated as an optional source of **precursors**, never as the final authority. The final asset is compiled locally, represented as `grid.json`, rendered again from that grid, reopened from disk, and accepted only when every hard validation rule passes.

## What it is for

Use Native Pixel Art when an asset must satisfy technical constraints that an image generator or ordinary resize workflow cannot reliably guarantee:

- exact native dimensions for sprites, icons, tiles, portraits, effects, or sprite sheets;
- a fixed palette, an exact color count, or a maximum color count;
- fully opaque pixels or binary transparency only;
- shared palette, frame layout, anchor, and baseline rules for animation;
- visual consistency with an existing game project;
- deterministic local compilation and machine-readable build records;
- safe promotion into a project only after validation succeeds.

The package can be used in two ways:

1. As the `native-pixel-art` Codex Skill.
2. As the standalone `pixel-art` command-line tool.

## Core guarantees

- `final.png` has the requested native dimensions.
- Visible colors obey the requested palette and count rule.
- Alpha values are restricted to `0` or `255`.
- Fully transparent pixels store RGB as `0,0,0`.
- `grid.json` is the canonical pixel representation.
- The preview is an exact integer nearest-neighbor enlargement.
- Animation frames use one palette and obey the requested sheet layout.
- A failed hard validation returns a nonzero exit code and blocks promotion.
- Existing output is not replaced unless `overwrite` is explicitly enabled.

## Requirements

- Python 3.11 or newer
- Windows, macOS, or Linux
- Optional: an OpenAI API key and the `openai` extra for headless image generation
- Optional: Aseprite for `.aseprite` export

## Installation

### Using uv

```bash
git clone https://github.com/hyfzero/native-pixel-art.git
cd native-pixel-art
uv sync --extra dev
uv run pixel-art --help
```

Add headless OpenAI image generation support:

```bash
uv sync --extra dev --extra openai
```

### Using pip

```bash
git clone https://github.com/hyfzero/native-pixel-art.git
cd native-pixel-art
python -m venv .venv
```

Activate the virtual environment, then install the package:

```bash
python -m pip install -e ".[dev]"
pixel-art --help
```

For headless OpenAI generation:

```bash
python -m pip install -e ".[dev,openai]"
```

Run a health check after installation:

```bash
pixel-art doctor
```

When using `uv` without activating an environment, prefix commands with `uv run`, for example `uv run pixel-art doctor`.

## Quick start: compile a local image

The fastest offline workflow turns an existing PNG into a strict 16×16, two-color asset:

```bash
pixel-art compile source.png \
  --width 16 \
  --height 16 \
  --palette "#000000,#FFFFFF" \
  --output output/icon
```

PowerShell uses a backtick for line continuation:

```powershell
pixel-art compile source.png `
  --width 16 `
  --height 16 `
  --palette "#000000,#FFFFFF" `
  --output output/icon
```

The command prints the path to `final.png`. The output directory also contains the canonical grid, preview, palette strip, manifest, and validation report.

For production work, prefer a versioned YAML or JSON request:

```yaml
schema_version: 2
asset_id: moon_icon
description: A small crescent moon icon with a clean, readable silhouette.
asset_type: static
style_profile: generic
width: 16
height: 16

palette:
  mode: fixed
  colors: ["#000000", "#FFFFFF"]
  color_count: 2
  count_rule: exact
  source: request

alpha:
  mode: binary

background:
  mode: transparent
  color: "#000000"

composition:
  subject_scale: 0.8
  alignment: center
  padding: 1

references:
  mode: none
  minimum: 0
  maximum: 0

cleanup:
  remove_isolated_pixels: true
  minimum_cluster_size: 2
  binary_alpha: true
  connectivity: 4

export:
  output_dir: output/moon_icon
  preview_scale: 12
  save_manifest: true
  save_intermediate: true
  overwrite: false
  promote: false
  aseprite: auto
```

Compile with the request:

```bash
pixel-art compile source.png --config request.yaml
```

## Main workflows

### 1. Offline compilation

Use a local illustration, render, sketch, generated image, or sprite sheet as the precursor:

```bash
pixel-art compile precursor.png --config request.yaml
```

The compiler:

1. resolves project and style-profile defaults;
2. loads project references when requested;
3. segments the background and crops the subject;
4. places the subject on a controlled working canvas;
5. downsamples to the native frame size;
6. selects or extracts the palette;
7. quantizes and cleans connected pixel clusters;
8. applies bounded request patches;
9. writes `grid.json`;
10. renders `final.png` from the grid;
11. independently validates the saved PNG and preview;
12. publishes the staging directory atomically.

This path does not use the network.

### 2. Headless OpenAI generation

Install the `openai` extra and set `OPENAI_API_KEY`.

PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Bash:

```bash
export OPENAI_API_KEY="your-api-key"
```

Use an explicit request:

```yaml
schema_version: 2
asset_id: forest_ranger
description: A small side-view forest ranger with a readable hat and bow.
asset_type: static
width: 32
height: 32
palette:
  mode: adaptive
  color_count: 8
  count_rule: maximum
  source: source
references:
  mode: none
  minimum: 0
  maximum: 0
generation:
  provider: openai
  variants: 3
  allow_image_generation: true
  model: gpt-image-2
  quality: medium
export:
  output_dir: output/forest_ranger
```

Then run:

```bash
pixel-art generate --config ranger.yaml
```

The backend creates the requested candidates, scores them for silhouette, padding, coverage, contrast, color complexity, and structural loss, then compiles the strongest candidate. A seed is intentionally rejected because the configured image model does not claim seed support.

### 3. Codex ImageGen handoff

Set:

```yaml
generation:
  provider: codex_imagegen
  variants: 3
  allow_image_generation: true
```

Then run:

```bash
pixel-art generate --config request.yaml
```

This prepares an `imagegen_handoff.json`, reference contact sheet, and reference statistics. Use those local references with Codex ImageGen, save the selected precursor, then compile it:

```bash
pixel-art compile selected-precursor.png --config request.yaml
```

The handoff command exits as a backend handoff rather than pretending that the CLI called the in-app ImageGen tool itself.

### 4. Animation sheets

A four-frame 32×32 walk cycle in a 4×1 sheet:

```yaml
schema_version: 2
asset_id: hero_walk
description: Four-frame side-view walk loop.
asset_type: animation
width: 32
height: 32
palette:
  mode: fixed
  colors: ["#000000", "#FEFEFE"]
  color_count: 2
  count_rule: exact
alpha:
  mode: binary
references:
  mode: none
  minimum: 0
  maximum: 0
animation:
  frame_width: 32
  frame_height: 32
  frame_count: 4
  columns: 4
  rows: 1
  baseline_tolerance: 2
  anchor_tolerance: 2
  actions:
    - name: walk
      start: 0
      count: 4
      fps: 8
export:
  output_dir: output/hero_walk
```

Compile an existing precursor sheet:

```bash
pixel-art animate --source precursor-sheet.png --config animation.yaml
```

The final sheet must be exactly `frame_width × columns` by `frame_height × rows`. Requested frames must be non-empty, unused cells must remain empty, and anchor/baseline drift must stay within tolerance.

### 5. Independent validation

Validate a PNG using the same request:

```bash
pixel-art validate output/moon_icon/final.png --config request.yaml
```

Or use direct constraints:

```bash
pixel-art validate \
  --input output/moon_icon/final.png \
  --width 16 \
  --height 16 \
  --max-colors 2 \
  --palette "#000000,#FFFFFF" \
  --report output/moon_icon/manual-validation.json
```

Validation reopens the file and does not call compiler repair functions. A hard failure exits with code `4`.

### 6. Palette and preview utilities

Extract a deterministic perceptual palette:

```bash
pixel-art palette extract source.png --colors 8 --output palette.json
pixel-art palette extract source.png --colors 8 --output palette.png
```

Create an exact nearest-neighbor preview:

```bash
pixel-art preview final.png --scale 12 --output preview.png
```

Analyze one image or a directory:

```bash
pixel-art analyze-style \
  --input assets/characters \
  --name room_characters \
  --output style.json
```

## Request configuration reference

Unknown request fields are rejected. This catches misspellings and stale configuration early.

| Section | Important fields | Meaning |
| --- | --- | --- |
| Identity | `schema_version`, `asset_id`, `description`, `asset_type` | Stable asset identity and intent. `asset_id` must be snake_case. |
| Geometry | `width`, `height` | Native size for static assets and tiles. |
| Animation | `frame_width`, `frame_height`, `frame_count`, `columns`, `rows`, `actions` | Per-frame size and sheet contract. |
| Palette | `mode`, `colors`, `color_count`, `count_rule`, `source` | Fixed, adaptive, profile, or semantic palette behavior. |
| Alpha | `mode`, `transparent_counts_as_color` | Binary or fully opaque output. |
| Background | `mode`, `color` | Transparent, solid, or preserved background. |
| Composition | `subject_scale`, `alignment`, `padding` | Subject placement before native-size reduction. |
| References | `mode`, `paths`, `category`, `minimum`, `maximum` | Explicit or automatic project-reference selection. |
| Generation | `provider`, `variants`, `allow_image_generation`, `model`, `quality` | Offline, Codex handoff, or headless OpenAI behavior. |
| Cleanup | `remove_isolated_pixels`, `minimum_cluster_size`, `connectivity`, `protected_mask` | Connected-region cleanup rules. |
| Patches | `operation`, `frame`, `x`, `y`, `width`, `height`, `color`, `transparent` | Bounded grid edits for semantic pixel fixes. |
| Export | `output_dir`, `preview_scale`, `overwrite`, `promote`, `promote_to`, `aseprite` | Output, replacement, and promotion behavior. |

The generated JSON Schema is available at [`schemas/request.schema.json`](schemas/request.schema.json). Complete field notes are in [`references/request_contract.md`](references/request_contract.md).

### Palette modes

- `fixed`: only listed colors may appear.
- `adaptive`: extract a deterministic palette from the source or references.
- `profile`: use project style-profile defaults.
- `semantic`: allocate palette budgets to configured semantic roles and masks.

`count_rule: exact` requires exactly `color_count` counted colors. With a fixed palette, every listed color must actually be used. The tool does not insert meaningless filler pixels to make validation pass.

### Background and alpha

- `background.mode: transparent` estimates and removes a separable border background.
- `background.mode: solid` composites onto `background.color`.
- `background.mode: preserve` retains source background behavior.
- `alpha.mode: binary` thresholds alpha to `0` or `255`.
- `alpha.mode: opaque` composites transparency onto the background color.

When a fixed palette and solid background are used together, the background color must belong to the fixed palette.

### Pixel patches

Patches operate on the canonical frame grid, not directly on `final.png`:

```yaml
patches:
  - operation: set_pixel
    frame: 0
    x: 7
    y: 5
    color: "#FFFFFF"
  - operation: fill_rect
    frame: 0
    x: 3
    y: 12
    width: 2
    height: 1
    transparent: true
```

Patch colors must belong to the canonical palette. Use patches only for bounded semantic repairs such as an eye, silhouette break, or animation anchor correction.

## Project-aware integration

For a game repository, keep project-specific policy under:

```text
tools/pixel_art/
├── project.yaml
├── profiles/
│   └── your_profile.yaml
├── reference_catalog.yaml
└── requests/
```

Example `tools/pixel_art/project.yaml`:

```yaml
schema_version: 1
work_dir: .godot/pixel_art_work
reference_catalog: reference_catalog.yaml
promotion_roots:
  - assets/generated
profiles:
  game_world_duotone: profiles/game_world_duotone.yaml
  room_color: profiles/room_color.yaml
```

Example profile:

```yaml
schema_version: 1
name: game_world_duotone
request_defaults:
  palette:
    mode: fixed
    colors: ["#000000", "#FEFEFE"]
    color_count: 2
    count_rule: exact
  style:
    dithering: off
  references:
    mode: auto
    minimum: 3
    maximum: 6
```

Build or refresh the reference catalog:

```bash
pixel-art profile-project --project-root /path/to/game
```

The current profiler scans PNG files under `assets/`, recognizes `game_world` and `room` paths, infers asset categories from directories, and writes:

- `tools/pixel_art/reference_catalog.yaml`
- `tools/pixel_art/style_stats.json`

Review generated categories and weights before committing them. Automatic reference selection ranks matching profiles using category match, configured weight, and logarithmic distance from the requested native size.

Check the integration:

```bash
pixel-art doctor --project-root /path/to/game
```

## Output contract

A normal compile can produce:

```text
output/<asset_id>/
├── final.png
├── grid.json
├── preview_12x.png
├── palette.png
├── manifest.json
├── validation_report.json
├── candidate_scores.json          # generated candidates only
├── intermediate/                  # when save_intermediate is true
├── references/
│   ├── reference_stats.json
│   └── reference_contact_sheet.png
└── <asset_id>.aseprite            # when available/requested
```

`manifest.json` records the normalized request, prompt plan, palette, references, candidate scores, frame metrics, compiler statistics, file hashes, backend metadata, semantic review, and promotion destinations.

## Safe promotion

Promotion copies validated artifacts into a project asset directory:

```yaml
export:
  output_dir: .godot/pixel_art_work/goblin_16
  promote: true
  promote_to: assets/generated/enemies
  overwrite: false
```

Promotion occurs only after hard validation passes. When `promotion_roots` are configured, destinations outside those roots are rejected. The operation stages files and uses backups so partial failures can be rolled back.

The promoted names are:

- `<asset_id>.png`
- `<asset_id>.grid.json`
- `<asset_id>.pixel-art.json`
- optional `<asset_id>.aseprite`

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `2` | Configuration, schema, input, or compile error |
| `3` | Image backend unavailable, refused, or handoff required |
| `4` | Hard asset validation failure |
| `5` | Required doctor check failed |
| `6` | Output already exists and overwrite was not enabled |

## Troubleshooting

### Output already exists

Use a new output directory or explicitly enable replacement:

```bash
pixel-art compile source.png --config request.yaml --overwrite
```

### Exact palette validation fails

Do not add an unrelated pixel just to satisfy the count. Improve the precursor, choose a more appropriate palette, change `exact` to `maximum` if the requirement allows it, or add a semantically justified patch.

### Small details disappear

Increase native dimensions, simplify the source, reduce visual clutter, disable cluster cleanup, lower `minimum_cluster_size`, or protect intentional details with a mask or bounded patch.

### Subject touches the border

Increase `composition.padding`, lower `composition.subject_scale`, or improve foreground/background separation in the precursor.

### OpenAI generation fails

Confirm all three requirements:

1. install the `openai` optional dependency;
2. set `OPENAI_API_KEY`;
3. set `generation.allow_image_generation: true`.

Then run `pixel-art doctor`.

### Aseprite is unavailable

Use `export.aseprite: auto` to keep it optional, `off` to disable it, or `required` when its absence must fail the build.

## More documentation

- [Development Guide](DEVELOPMENT.md)
- [Request contract](references/request_contract.md)
- [Complete request examples](references/examples.md)
- [Project style configuration](references/project_styles.md)
- [Palette rules](references/palette_rules.md)
- [Connected-cluster rules](references/cluster_rules.md)
- [Prompt planning rules](references/prompting.md)

## License

No license file is currently included. Add one before distributing or accepting external contributions under a defined license.
