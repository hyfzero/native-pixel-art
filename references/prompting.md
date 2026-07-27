# Prompt planning rules

Use a strong silhouette, a complete subject, safe padding, large connected color regions, low detail, minimal gradients, and clean foreground/background separation in every precursor prompt.

## Size adaptation

- At 8 pixels or below: allow one iconic subject, no face, thin line, texture, or complex background, and two to four color blocks.
- At 16 pixels or below: retain one or two identifying features, represent eyes as high-contrast points, simplify clothing, and target four to eight colors.
- At 32 pixels or below: allow a simple expression and limited clothing detail, cap each material at three shades, and target six to twelve colors.
- Above 32 pixels: retain connected shapes and controlled ramps; reject photorealistic noise and micro-detail.

Always forbid text, watermarks, smooth gradient backgrounds, anti-aliased micro-detail, and cropped subject parts.
