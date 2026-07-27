---
name: native-pixel-art
description: Generate or compile project-aware native pixel art under exact PNG dimensions, palette count or membership constraints, binary alpha rules, animation grid contracts, deterministic grid rendering, and independent validation. Use for strict sprites, icons, portraits, tiles, effects, or spritesheets, especially when project reference images must guide GPT Image while local code controls the final pixels.
---

# Native Pixel Art

Treat every image-model result as a precursor, never as the final game asset. The authoritative asset is rendered locally from `grid.json`, reopened from disk, and accepted only after independent validation.

## Required workflow

1. Identify the exact asset type, frame dimensions, frame layout, visible-color rule, alpha rule, project style profile, category, and promotion target.
2. Run `pixel-art doctor --project-root PROJECT` when the CLI origin or environment has not been checked in the current task.
3. Prefer a versioned YAML/JSON `PixelArtRequest`. Read [request_contract.md](references/request_contract.md) for the full contract.
4. Resolve 3–6 project references by category and nearby native size. Use explicit references when the user names assets. Generate the catalog with `profile-project` only when it is missing or intentionally being refreshed.
5. Write the contact sheet and reference statistics before image generation.
6. Choose one precursor path:
   - Existing/local image: run `pixel-art compile SOURCE --config REQUEST`.
   - Codex ImageGen: prepare the structured handoff, inspect the contact sheet, call the `imagegen` tool with the selected local references, then compile its saved result.
   - Headless OpenAI: use `pixel-art generate --config REQUEST` only when `generation.provider=openai`, `allow_image_generation=true`, and `OPENAI_API_KEY` is available.
7. For three requested candidates, inspect native-scale silhouette, orientation, subject completeness, cell boundaries, and project-style fit; compile the strongest candidate.
8. Let the compiler segment, crop, downsample, select/map the palette, clean connected clusters, write `grid.json`, and render `final.png` from that grid.
9. If a semantic one-pixel feature or animation anchor needs repair, add only bounded `patches` to the request and recompile. Allow at most two repair rounds. Never add an unrelated corner pixel just to satisfy an exact color count.
10. Require the independent validator to reopen the PNG and pass every hard invariant before promotion.
11. Use `export.promote=true` only when the user explicitly wants a validated asset copied into the project asset tree. Never edit Godot scenes or `.godot` import artifacts as part of this Skill.

## Commands

```powershell
pixel-art doctor --project-root D:\path\to\project
pixel-art profile-project --project-root D:\path\to\project
pixel-art compile precursor.png --config request.yaml
pixel-art generate --config request.yaml
pixel-art animate --source precursor_sheet.png --config animation.yaml
pixel-art validate output\final.png --config request.yaml
pixel-art analyze-style --input assets\characters --name room_characters --output style.json
```

The compatibility commands `generate`, `analyze-style`, `animate`, and `validate` also accept their former direct flags. `compile`, `profile-project`, and `doctor` use the same installed package and request model.

## Project profiles

When a repository contains `tools/pixel_art/project.yaml`, use its profile and reference catalog. Read [project_styles.md](references/project_styles.md) before changing project profile defaults.

- `game_world_duotone`: default visible colors are exactly `#000000` and `#FEFEFE`; transparent pixels are allowed and do not count. Favor connected silhouettes, sparse details, and single-pixel semantic features. No dithering, anti-aliasing, or half-alpha.
- `room_color`: default to exactly 12 visible colors selected deterministically in Lab space from same-type Room assets. Favor warm ramps, readable dark outlines, and conventional colored pixel-art proportions.

An explicit request may override `#FEFEFE` with `#FFFFFF` or change a color count. Preserve the explicit request.

## Hard invariants

- `final.png` has the exact requested native dimensions; an animation sheet has exact frame size × layout dimensions.
- Visible colors obey `exact` or `maximum` count rules and fixed-palette membership. In `exact`, every required fixed color must actually be used.
- Alpha values are only `0` or `255`; opaque mode contains no transparent pixels.
- Fully transparent pixels store RGB `0,0,0`.
- The compiler never emits anti-aliased or illegal colors after palette mapping.
- Animation frames share one palette; requested frames are non-empty; unused cells are empty; anchor and baseline drift stay within tolerance.
- The preview is an integer-scale, pixel-for-pixel nearest-neighbor enlargement.
- Any hard failure returns nonzero and blocks promotion.

## Output contract

Keep temporary work in the project-configured `.godot/pixel_art_work/` directory. A compile produces:

- `final.png`
- `grid.json`
- `preview_Nx.png`
- `palette.png`
- `manifest.json`
- `validation_report.json`
- reference contact sheet and statistics
- frame manifest for animations
- optional `.aseprite` when Aseprite is detected

The manifest records the normalized request, references, prompt plan, hashes, compiler statistics, backend metadata, and promotion destinations.

## Failure handling

- Configuration/schema error: exit `2`.
- Image backend unavailable or refused: exit `3`.
- Hard asset validation failure: exit `4`.
- Doctor failure: exit `5`.
- Duplicate output without overwrite: exit `6`.

On validation failure, retain the staging result and report for diagnosis but do not promote it. On generation or compiler interruption, remove only that run’s temporary directory.
