# Assignment 1: Grower Web Map

A lightweight, standalone interactive HTML map generator for grower-level field
boundaries. Built as a subskill inside the My Farm Advisor data-pipeline.

## Overview

This subskill reads the field boundary GeoJSON produced by the data pipeline
and emits a single self-contained HTML file that can be opened directly in any
modern web browser.

The map shows all fields for a grower on an OpenStreetMap basemap, lets users
zoom and pan, click fields for metadata popups, and use a sidebar to jump to
individual fields.

## Output

```text
growers/<grower>/farms/<farm>/derived/dashboards/<farm>_grower_webmap.html
```

The HTML file embeds the GeoJSON inline and loads Leaflet.js from a CDN. It
requires no server, no build step, and no external data files at runtime.

## Prerequisites

- A working My Farm Advisor data-pipeline runtime.
- Field boundary GeoJSON already generated (e.g., via `farm_dashboard.py create`).

## Quick Start

### 1. Install the runtime source (copies this script into the live runtime)

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

### 2. Generate the map

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm
```

### 3. Open the result

```bash
open "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/northern-illinois-grower/farms/illinois-farm/derived/dashboards/illinois-farm_grower_webmap.html"
```

## Map Features

- **Basemap:** OpenStreetMap (loads from the internet).
- **Field polygons:** All fields rendered from the actual downloaded boundary
  GeoJSON.
- **Click popup:** Shows grower, farm, field ID, area (acres), and crop name.
- **Sidebar:** Lists every field with ID, area, crop, and a "Zoom" button.
- **Zoom to field:** Click the Zoom button or the row to pan, zoom, and open
  the field popup.
- **Fit bounds:** Map automatically centers and zooms to show all fields on load.
- **Responsive:** Adapts layout for mobile screens.

## Command-line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--grower-slug` | `AG_GROWER_SLUG` env var | Grower identifier |
| `--farm-slug` | `AG_FARM_SLUG` env var | Farm identifier |
| `--output-filename` | `<farm>_grower_webmap.html` | Override output filename |

## File Size

For a typical farm with 3–12 fields, the HTML output is roughly **40–150 KB**.
No imagery, rasters, or raw data bundles are embedded.
