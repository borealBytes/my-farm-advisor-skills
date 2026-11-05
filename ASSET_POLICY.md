# Asset Policy

## Repository hygiene

- Do not commit generated or downloaded runtime assets.
- Keep build artifacts, cache directories, and generated outputs out of Git.
- Geoadmin payloads such as `countries.geojson` and `states_usa.geojson` are runtime data, not repository content.

## Runtime data lives outside Git (the `data` rule)

Repository-tracked content is instructions, scripts, and small fixtures — never operational data. Farm/agricultural data is **payload, not source**: its size grows roughly linearly with the acreage and field count under monitoring (boundary tiles, soil profiles, DEM clips, satellite scenes, weather series, classification patches), so it must live in a dedicated, gitignored runtime data directory rooted at the `DATA_PIPELINE_DATA_ROOT` environment variable (default `./data`), never inside the skill tree. A clone of this repository must stay small and complete regardless of how many farms, fields, or acres any deployment tracks.

## Checked-in example outputs (the one exception)

Generated outputs are permitted in Git at **exactly one location**: small, deterministic demonstration fixtures under `examples/**/output/` inside a skill directory. These exist so a reader can verify an example end-to-end offline. Generated outputs anywhere else in the repository remain excluded — regenerate or download them at runtime instead of tracking them with Git or Git LFS.

## Large file handling

- Binary assets larger than 1 MB must use Git LFS (the `examples/**/output/` fixture exception still applies to this cap).
- Required LFS-backed formats in this repo include `.npy`, `.npz`, `.raw`, `.bin`, `.so`, `.dylib`, and `.dll`.
- JSON and GeoJSON metadata files remain normal text files and must not be moved to Git LFS by default.

## Review requirements

- Any large file addition requires explicit reviewer approval.
- If a file should be regenerated or downloaded at runtime, exclude it instead of tracking it with Git or Git LFS.
