# Grower Web Map — Usage Guide

## Overview

Generates a lightweight self-contained HTML map per grower showing all farm field boundaries with interactive NDVI, soil, and crop-type layers on Leaflet.js maps. No server needed — the HTML file embeds GeoJSON directly and loads basemap tiles from public CDNs.

## Prerequisites

- `DATA_PIPELINE_DATA_ROOT` set to the runtime root (e.g., `~/my-farm-advisor-runtime`)
- Runtime venv installed (via `data-pipeline/scripts/install.sh`)
- At least one grower exists under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`
- Each grower has at least one farm with `boundary/field_boundaries.geojson`
- NDVI composite TIFs and SSURGO soil summary CSV for enrichment

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
export DATA_PIPELINE_VENV_DIR="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv"

"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug <grower-slug>
```

## Output

The HTML file is written to:
```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower-slug>/maps/grower_web_map.html
```

Open the HTML file directly in any modern browser to view the map.

## Layers

| Layer | Description | Data Source |
|-------|-------------|-------------|
| **Field Boundaries** | Default view — white field polygons with orange hover | `field_boundaries.geojson` |
| **NDVI** | Choropleth colored by mean NDVI (latest year) | Yearly composite TIF → zonal mean |
| **Soil: OM%** | Colored by organic matter percentage | `ssurgo_summary.csv` |
| **Soil: pH** | Colored by pH (optimal green, extremes red) | `ssurgo_summary.csv` |
| **Crop Type** | Placeholder when CDL data unavailable | — |
| **Soil Polygons (checkbox)** | SSURGO soil map unit boundaries overlay | `ssurgo_soil_types.geojson` |

## Map Features

- **Dual basemaps:** Esri Satellite (default) and OpenStreetMap streets, toggled via top-right layer control
- **Layer switcher:** Radio buttons in sidebar to switch between NDVI, soil OM%, soil pH, and crop type views
- **Soil polygon overlay:** Toggle SSURGO map-unit boundaries with a checkbox
- **Choropleth coloring** with dynamic legend that updates per layer
- **Click a field** to see enhanced popup with: Grower, Farm, Field, Area, County, NDVI stats, dominant soil, OM, pH, AWS, CEC, drainage class, erosion risk
- **Sidebar field list** — click any field to zoom and open popup; sidebar shows metric per field (area, NDVI, OM, or pH depending on active layer)
- **Pan and zoom** enabled
- **Canvas renderer** for smooth performance
- **Small file size** — typically 15–30 KB per grower (GeoJSON + summary values only, no rasters)

## Examples

```bash
# Generate map for Illinois grower
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
export DATA_PIPELINE_VENV_DIR="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv"
"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug il-grower

# Generate map for Iowa grower
"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug ia-grower
```

## Output structure

```
growers/<grower-slug>/
  maps/
    grower_web_map.html       ← generated HTML map
  farms/
    <farm-slug>/
      boundary/
        field_boundaries.geojson  ← input boundary data
```

## Customization

Edit `src/scripts/reporting/generate_grower_web_map.py` to change:
- Layer color ramps (NDVI, OM, pH breakpoints and colors)
- Popup content and layout
- Additional soil properties (clay, sand, CEC, AWS) as new layers
- Sidebar behavior
- Basemap tile URLs

After editing, sync the source: `./scripts/install.sh --force-refresh --no-install-deps`
