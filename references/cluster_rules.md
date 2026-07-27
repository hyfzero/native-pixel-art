# Connected-cluster rules

- Use 4-connectivity by default; opt into 8-connectivity only when diagonal contact should join regions.
- Detect isolated pixels and regions below `minimum_cluster_size` independently per visible color.
- Preserve any pixel selected by a protected mask.
- Merge a small region into the visually nearest adjacent color; remove it to transparency when no visible neighbor exists.
- Record component counts, merged pixels, isolated counts, and a basic outline-break warning before and after cleanup.
- Keep cleanup optional because intentional single-pixel eyes, highlights, and antennae can be semantically important.
- Protect intentional one-pixel semantic features with a mask or a bounded request patch.
- Apply patches to frame-local palette indices, never directly to the final PNG.
- Limit automated repair to two rounds and re-run every hard validator after each round.
