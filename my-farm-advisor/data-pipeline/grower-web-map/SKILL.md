---
name: grower-web-map
description: >
  Lightweight per-farm interactive Leaflet maps for existing My Farm Advisor
  growers. Use when a request needs a self-contained HTML map with Esri World
  Imagery, real pipeline field polygons, toggleable SSURGO soil and yearly NDVI
  overlays, click-through grower/farm/field metadata, zoom, and a field list.
license: Apache-2.0
metadata:
  author: InsightAgScouting
  version: "0.1.0"
  skill-author: InsightAgScouting
  skill-version: "0.1.0"
---

# Grower Web Map

Generate one small, self-contained interactive HTML map per farm from the field boundaries, soil polygons, and NDVI composites the data pipeline already wrote. Output is runtime-only and never committed.

## Start Here

- Read [README.md](README.md) for install/seeding, CLI, output contract, layer behavior, and troubleshooting.
- Read [INDEX.md](INDEX.md) for file-level navigation.
- Open [`src/grower_web_map/builder.py`](src/grower_web_map/builder.py) for boundary loading, soil/NDVI payloads, metadata extraction, and the HTML template.

## When to Invoke

- A grower or farm needs a browser-viewable field map with satellite imagery.
- Someone wants to inspect field layout, soil map units, or NDVI side by side without ArcGIS/QGIS.
- A demo, review, or handoff needs a single HTML file that can be emailed or hosted statically.

Do not use this skill for printed report figures, soil lab interpretation, or offline maps. For full soil or NDVI analysis, use the soil and imagery skills that produce the underlying rasters.

## Runtime Contract

| Item | Path |
| --- | --- |
| Inputs | `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson` |
| Fallback inputs | `.../fields/<field>/boundary/field_boundary.geojson` |
| Optional soil inputs | `.../fields/<field>/soil/ssurgo_soil_types.geojson`, `.../soil/ssurgo_full.csv` |
| Optional NDVI inputs | `.../fields/<field>/derived/features/ndvi_year_<year>_composite.tif` |
| Output | `.../farms/<farm>/derived/dashboards/<farm>_fields_map.html` |

The map uses the real downloaded polygons and rasters from pipeline output. Soil polygons are embedded as coordinates; NDVI rasters are reduced to small clipped PNGs. Original imagery, GeoTIFFs, and report bundles are never embedded.

The soil overlay needs only the standard library. NDVI needs `numpy`, `rasterio`, and `Pillow` and is skipped with a warning when they are unavailable, so the map still builds.

## Commands

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
PYTHONPATH="$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/src" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" -m grower_web_map --all-growers
```

Use `--grower-slug <grower>` for one grower. See [README.md](README.md) for seeding the subskill into an existing runtime.

## Layers

- Field boundaries (on by default), SSURGO soils, and NDVI, each toggled from the layers control.
- Soils: one polygon per map unit per field, categorical palette, sidebar legend with `mukey`, series, drainage, acres, and percent of field.
- NDVI: one overlay with year chips for 2021–2025. Fixed `-0.2`–`1.0` `RdYlGn` scale matching the farm report's NDVI cards.
- Keep the NDVI overlay clipped to the field boundary; the composites are padded boxes and would otherwise cover neighbouring ground.

## Basemap and Attribution

- Basemap: Esri World Imagery tiles (internet required).
- Second layer: OpenStreetMap streets.
- Mapping library: Leaflet 1.9.4 from unpkg.
- Keep the Esri and OpenStreetMap attributions visible in any reuse.
