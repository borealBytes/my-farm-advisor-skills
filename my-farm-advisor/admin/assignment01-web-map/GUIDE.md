---
name: assignment01-web-map
description: Generate a lightweight, self-contained interactive HTML web map per grower using actual field boundary GeoJSON from the data-pipeline runtime.  No embedded imagery—only embedded polygon metadata with Leaflet.js and an external basemap.
version: 1.0.0
author: Boreal Bytes
tags: [web-map, visualization, leaflet, geospatial, interactive, grower, assignment-1]
---

# Workflow: assignment01-web-map

## Description

Create a **single, self-contained HTML file** per grower that visualises all
field polygon boundaries on an interactive map.  The map is intentionally
lightweight: it embeds only the GeoJSON feature collection (with enriched
metadata) and loads Leaflet.js plus a CartoDB basemap from CDN.  No raster
imagery, NDVI composites, soil choropleths, or weather charts are included.

**Key Features**

- **Self-contained GeoJSON** – all field polygons and metadata are embedded in the HTML
- **External basemap** – CartoDB Positron (light) tiles load from the internet
- **Click-to-popup** – clicking a field reveals grower name, farm name, field name, county, and area
- **Sidebar field list** – a scrollable list of fields; clicking an item zooms to that field and opens its popup
- **Auto-fit bounds** – the map initially zooms to fit all fields for the grower
- **Zoom & pan** – standard Leaflet interaction

## When to Use This Workflow

- **Assignment 1 deliverable** – satisfy the grower web-map requirement
- **Quick reference** – share a lightweight field map with stakeholders
- **Mobile friendly** – open the HTML on any tablet or phone with a network connection

## Prerequisites

1. A working My Farm Advisor data-pipeline runtime with at least one grower and
   one farm that has field boundary GeoJSON.
2. `DATA_PIPELINE_DATA_ROOT` exported to the runtime path.

## Quick Start

### 1. Run from the checkout (copies into runtime automatically via install)

If you are iterating on the script in the skill checkout, run the installer so
the runtime receives the latest `src/` copy:

```bash
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive
```

### 2. Generate a map for a single grower

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/admin/generate_grower_webmap.py --grower-slug illinois-grower
```

### 3. Open the result

```bash
open "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/illinois-grower/derived/grower_webmap.html"
```

## Python API Reference

The subskill exposes a minimal wrapper class for programmatic use.

### `Assignment01WebMapSkill`

```python
from assignment01_web_map import Assignment01WebMapSkill

skill = Assignment01WebMapSkill()
output_path = skill.create_map(
    grower_slug="illinois-grower",
    output_dir=Path("/tmp/maps")
)
```

#### Methods

- **`create_map(grower_slug, output_dir=None) -> Path`**  
  Discover all farms for the grower, read their `boundary/field_boundaries.geojson`,
  enrich features with metadata from `grower.json`, `farm.json`, and per-field
  `field.json`, and write a single HTML file.

## Output Standards

- **File name**: `grower_webmap.html`
- **Location**: `growers/<grower-slug>/derived/grower_webmap.html`
- **Size**: Typically 10–50 KB for a handful of fields (scales linearly with polygon complexity)
- **Format**: Single-file HTML5 with embedded GeoJSON and remote CDN assets

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATA_PIPELINE_DATA_ROOT` | Yes | Absolute path to the runtime tree. |

## Related Workflows

- [Interactive Web Map Guide](../interactive-web-map/GUIDE.md) – heavy, full-featured maps with Folium, layer controls, and choropleths
- [Data Pipeline AGENTS.md](../../data-pipeline/AGENTS.md) – runtime contracts and pipeline commands
