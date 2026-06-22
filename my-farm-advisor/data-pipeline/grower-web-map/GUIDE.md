# Grower Web Map – Guide

## Description

Render a browser-ready interactive map for one or all farms
under a data-pipeline grower. The generator reads the farm's
`field_boundaries.geojson`, farm, and grower JSON metadata,
then writes a standalone HTML file with embedded field polygons.

## Map features

- OpenStreetMap basemap (internet required at view time)
- Mouse-wheel zoom, drag-pan, fit-to-bounds
- Each field rendered as a colored polygon
- Hover highlights field outline
- Click shows popup: grower slug, farm display name, field ID,
  area in acres, county, OSM land-use tag
- Sidebar panel with scrollable field list
- Click a field name to zoom the map to that field

## Usage

### Single farm

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower \
  --farm-slug il-grower-illinois
```

### All farms under a grower

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower
```

### Environment-only mode

When `AG_GROWER_SLUG` and optionally `AG_FARM_SLUG` are set in the
environment, no arguments are needed:

```bash
export AG_GROWER_SLUG=il-grower
export AG_FARM_SLUG=il-grower-illinois
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_map.py
```

### Output location

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/dashboards/grower_web_map.html
```

The `derived/dashboards/` directory is created automatically if it
does not exist.

## Dependencies

- Leaflet.js 1.9.4 (CDN, loaded by the generated HTML)
- No additional Python packages beyond the runtime venv
