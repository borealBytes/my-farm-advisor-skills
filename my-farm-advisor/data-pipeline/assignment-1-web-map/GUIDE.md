---
name: assignment-1-web-map
description: Generate lightweight interactive HTML web maps for grower farms
  from pipeline field boundary GeoJSON. Single-file Leaflet.js output with
  embedded data, sidebar field list, click popups, and zoom-to-field.
version: "1.0.0"
author: Superior Byte Works, LLC
---

# Assignment 1 — Grower Web Map

## Purpose

Produce a self-contained, browser-ready interactive map for any grower/farm
that has already run through the farm advisor data pipeline.

## Output

A single `.html` file per farm containing:
- OpenStreetMap basemap tiles (loaded from CDN)
- All field polygons from `boundary/field_boundaries.geojson`
- Distinct fill colors per field
- Click popups with grower, farm, field ID, area, crop, and county
- Left sidebar with a clickable field list (click zooms to field)
- Auto-fit bounds on load

## Prerequisites

- `DATA_PIPELINE_DATA_ROOT` exported and pointing to an initialized runtime
- The target grower/farm must have `boundary/field_boundaries.geojson`
- Python 3 + the runtime venv (GeoPandas is already installed)

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime

# Iowa grower
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/generate_grower_web_map.py" \
  northern-iowa-grower --farm-slug cerro-gordo-farm \
  --output ~/cerro-gordo-grower-map.html

# Illinois grower
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/generate_grower_web_map.py" \
  northern-illinois-grower --farm-slug dekalb-farm \
  --output ~/dekalb-grower-map.html
```

Open the resulting HTML in any modern browser.

## CLI Reference

```
generate_grower_web_map.py <grower_slug> --farm-slug <farm_slug> --output <path>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `grower_slug` | Yes | Grower directory name under `growers/` |
| `--farm-slug` | Yes | Farm directory name under the grower's `farms/` |
| `--output` | Yes | Path to write the `.html` file |

## Design Notes

- **No extra Python dependencies**: Uses only the existing GeoPandas in the
  runtime venv. Leaflet JS/CSS loads from unpkg CDN at view time.
- **No embedded imagery**: The HTML is ~20–40 KB depending on field count.
- **Idempotent**: Re-running overwrites the output file; no side effects on
  pipeline data.
