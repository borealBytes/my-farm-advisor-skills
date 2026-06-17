---
name: grower-web-map
description: Generate lightweight interactive Leaflet HTML maps per grower from field boundary data.
version: 1.0.0
tags: [web-map, leaflet, grower, field-boundaries]
---

# Guide: grower-web-map

## Description

Generates a self-contained interactive HTML web map for each grower in the
My Farm Advisor data pipeline runtime. The map uses Leaflet.js with OpenStreetMap
basemaps and embeds field polygon geometry directly in the HTML file.

## Prerequisites

The data-pipeline runtime must be initialized and at least one grower must exist
with field boundaries under:

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<slug>/
```

## Usage

### Generate maps for all growers

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py
```

### Generate a map for one grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py \
  --grower-slug il-grower
```

### Options

| Option | Default | Description |
|---|---|---|
| `--grower-slug` | (all growers) | Generate map for a single grower |
| `--output` | `grower_web_map.html` | Override output filename |

## Output

Each grower map is written to the farm's dashboard directory:

```
growers/<slug>/farms/<slug>/derived/dashboards/grower_web_map.html
```

## Opening the map

Open the HTML file in any modern web browser. Internet connection is required
for the basemap tiles and Leaflet library (loaded from CDN).

## Map features at a glance

- **Basemaps**: OpenStreetMap (default) + ESRI Satellite toggle
- **Fields**: Polygon overlay with semi-transparent green fill
- **Click popup**: grower, farm, field ID, county, area (acres)
- **Sidebar**: field list with zoom-to-field buttons, summary stats
- **Auto-zoom**: map fits all field boundaries on load

## Example output size

For 3 fields, the generated HTML is typically 30-80 KB (no rasters or heavy
data bundles embedded).
