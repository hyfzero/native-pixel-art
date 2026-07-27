# Palette rules

- Quantize after reduction, never before.
- Measure palette distance in Lab rather than raw RGB.
- Exclude fully transparent pixels from extraction and visible-color counts unless the request explicitly counts transparency.
- In fixed mode, map only to supplied colors and independently scan the saved PNG.
- In adaptive mode, sample each reference without letting a large source dominate merely because it has more pixels.
- `count_rule: exact` requires the exact visible-color count. A fixed exact palette also requires every member to appear.
- Never manufacture a meaningless corner pixel to satisfy `exact`. Fail validation and revise the source, palette, or a semantically justified patch.
- Keep dithering off for project profiles. Do not diffuse errors through transparent pixels or across high-contrast outline boundaries.
- Set RGB to black under full transparency after every repair.
- Treat semantic allocation without role masks as a baseline, not full segmentation.
