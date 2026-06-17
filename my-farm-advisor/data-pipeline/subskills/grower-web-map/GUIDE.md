# Grower Web Map Guide

## Overview

Generate lightweight Leaflet-based interactive HTML maps for every grower in the pipeline. Each map shows all fields across all farms for that grower, color-coded by farm, with a clickable sidebar field list.

## Prerequisites

- Data pipeline runtime installed at `$DATA_PIPELINE_DATA_ROOT`
- At least one grower with field boundaries generated
- The data-pipeline venv (all dependencies already installed)

## Generate Maps

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_maps.py
```

## Output

Each grower gets one file:

```
growers/<grower-slug>/derived/reports/<grower-slug>_fields_map.html
```

Open any `.html` file directly in a browser (no server required).

## Features

| Feature | Description |
|---------|-------------|
| Farm-colored polygons | Each farm gets a distinct color; legend shown via polygon border colors |
| Click popups | Field ID, Farm, Grower, County, Acres, Crop |
| Field sidebar | Clickable list of all fields; click to zoom and popup |
| Fit all fields | Button in sidebar resets the view to show all fields |
| OpenStreetMap basemap | Loaded from CDN; zoom/pan work as expected |

## Map size

Typically 50-150 KB per grower. Only GeoJSON geometry and properties are embedded — no rasters, imagery, or heavy data bundles.
