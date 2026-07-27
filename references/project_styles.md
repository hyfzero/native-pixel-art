# Project style configuration

Keep reusable implementation in this Skill. Keep repository-specific choices in:

```text
tools/pixel_art/
  project.yaml
  profiles/
  reference_catalog.yaml
  requests/
```

`project.yaml` declares config version, work directory, profile files, catalog, and legal promotion roots. A style profile supplies request defaults and multimodal guidance. Explicit request fields override profile defaults.

Reference catalog entries contain:

- project-relative PNG path;
- style profile;
- category;
- original width and height;
- intended reference purpose;
- selection weight.

Automatic selection ranks matching profiles by category, weight, and logarithmic size distance. Same-category images win; other same-world images may fill the minimum. Prefer 3–6 references.

`profile-project` scans source PNGs and produces a machine-readable catalog plus statistics. Review weights and categories before committing a refreshed catalog.
