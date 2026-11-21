---
name: grower-web-map
description: >
  Grower-level interactive HTML field map for My Farm Advisor runtime data. Use
  when a grower needs a lightweight, satellite-backed web map of every farm and
  field boundary with click-through metadata, zoom controls, and a
  zoom-to-field list. Reads pipeline boundary GeoJSON and writes one HTML file
  per grower outside Git; all areas are reported in hectares.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "0.1.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "0.1.0"
---

# Grower Web Map

Use this nested skill when someone asks for a **grower-level interactive map**: one
HTML page per grower that shows every farm and field polygon over satellite imagery
and exposes grower, farm, and field metadata on click.

The generator is read-only with respect to pipeline data. It consumes real runtime
boundaries, embeds only geometry plus a small attribute set, and loads basemap tiles
from Esri at view time. Areas are hectares, converted from the boundary file's
`area_acres` with `1 acre = 4046.8564224 m²`.

## Start Here

- Read [README.md](README.md) for inputs, outputs, runbook, map behavior, and limits.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Read [references/web-map-contract.md](references/web-map-contract.md) before changing the HTML, the embedded data shape, or the basemap.
- Open [`src/grower_web_map.py`](src/grower_web_map.py) for discovery, hectare conversion, and HTML rendering.
- Open [`scripts/generate_grower_web_map.py`](scripts/generate_grower_web_map.py) for the CLI flags and summary table.
- Run [`scripts/install.sh`](scripts/install.sh) to copy this subskill into an installed runtime.
- Read [PROVENANCE.md](PROVENANCE.md) for origin, data attribution, and tile terms.

## Routing Notes

- Invoke for requests such as "map the grower's fields", "interactive field map",
  "web map of all farms", "satellite field map", or "click a field for details".
- Use it only against an installed runtime (`DATA_PIPELINE_DATA_ROOT`); it does not
  create boundaries, soil, weather, or imagery products.
- Do not embed imagery, rasters, or full data bundles in the HTML. Keep the satellite
  basemap as online tiles and keep output under the runtime tree.
- Do not report acres in this map. Convert to hectares and keep the label and the
  number consistent.
- This subskill is not wired into `run_farm_pipeline.py`; run it explicitly after a
  grower has completed field-boundary ingest.
