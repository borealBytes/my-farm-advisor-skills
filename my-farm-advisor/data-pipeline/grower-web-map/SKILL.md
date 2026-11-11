---
name: grower-web-map
description: >
  Lightweight per-farm interactive Leaflet field maps for existing My Farm
  Advisor growers. Use when a request needs a self-contained HTML map with
  Esri World Imagery, real pipeline field polygons, click-through grower/farm/
  field metadata, zoom, and a field list.
license: Apache-2.0
metadata:
  author: InsightAgScouting
  version: "0.1.0"
  skill-author: InsightAgScouting
  skill-version: "0.1.0"
---

# Grower Web Map

Generate one small, self-contained interactive HTML map per farm from the field boundaries the data pipeline already wrote. Output is runtime-only and never committed.

## Start Here

- Read [README.md](README.md) for install/seeding, CLI, output contract, map behavior, and troubleshooting.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Open [`src/grower_web_map/builder.py`](src/grower_web_map/builder.py) for boundary loading, metadata extraction, and the HTML template.

## When to Invoke

- A grower or farm needs a browser-viewable field map with satellite imagery.
- Someone wants to inspect field layouts and basic attributes without ArcGIS/QGIS.
- A demo, review, or handoff needs a single HTML file that can be emailed or hosted statically.

Do not use this skill for analysis rasters, NDVI/soil grids, printed report figures, or offline maps. It embeds only field polygons and attributes.

## Runtime Contract

| Item | Path |
| --- | --- |
| Inputs | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` |
| Fallback inputs | `.../fields/<field>/boundary/field_boundary.geojson` |
| Output | `.../farms/<farm>/derived/dashboards/<farm>_fields_map.html` |

The map uses the real downloaded polygons from pipeline output. It never embeds imagery, rasters, or report bundles.

## Commands

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
PYTHONPATH="$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/src" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" -m grower_web_map --all-growers
```

Use `--grower-slug <grower>` for one grower. See [README.md](README.md) for seeding the subskill into an existing runtime.

## Basemap and Attribution

- Basemap: Esri World Imagery tiles (internet required).
- Second layer: OpenStreetMap streets.
- Mapping library: Leaflet 1.9.4 from unpkg.
- Keep the Esri and OpenStreetMap attributions visible in any reuse.
