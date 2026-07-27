# Complete examples

## Project duotone 16×16 sprite

```yaml
schema_version: 2
asset_id: goblin_16
description: A hunched side-facing goblin with pointed ears and one readable eye.
asset_type: static
style_profile: game_world_duotone
project_root: D:/Godot/safe-house-syndrome
width: 16
height: 16
palette:
  mode: fixed
  colors: ["#000000", "#FEFEFE"]
  color_count: 2
  count_rule: exact
references:
  mode: auto
  category: enemy
  minimum: 3
  maximum: 6
generation:
  provider: codex_imagegen
  variants: 3
  allow_image_generation: true
```

## Room 48×48 NPC

Use `style_profile: room_color`, `references.category: npc`, and the profile-default exact 12 visible colors. If compilation produces fewer meaningful colors, revise the source or request; do not insert filler pixels.

## Four-frame 32×32 animation

```yaml
asset_id: walk_4x32
description: Four-frame side-view walk loop.
asset_type: animation
style_profile: game_world_duotone
animation:
  frame_width: 32
  frame_height: 32
  frame_count: 4
  columns: 4
  rows: 1
  baseline_tolerance: 2
  anchor_tolerance: 2
  actions:
    - {name: walk, start: 0, count: 4, fps: 8}
```

The final sheet must be exactly 128×32. Every requested frame must be non-empty and use the sheet’s canonical palette.
