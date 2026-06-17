# Grower Web Map Subskill — Local Instructions

## Purpose

This subskill generates one lightweight Leaflet-based interactive HTML map per grower from the canonical field-boundary GeoJSON files produced by the data pipeline. Use it for rapid visual review of all fields across all farms for a given grower.

## Location

- **Script:** `src/scripts/reporting/generate_grower_web_maps.py`
- **Runtime copy:** `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_maps.py`
- **Output:** `growers/<grower-slug>/derived/reports/<grower-slug>_fields_map.html`

## Safe edit scope

Edits should stay in `generate_grower_web_maps.py` and this folder unless the user explicitly asks for broader changes.

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_web_maps.py
```

The script auto-discovers all growers with field boundaries under `growers/` and generates one map per grower.

## Output

Each HTML file is self-contained, loads Leaflet.js and OpenStreetMap tiles from CDN, and includes:

- Farm-colored field polygons
- Click popups with field metadata (grower, farm, field_id, county, acres, crop)
- Sidebar with clickable field list (click to zoom to field)
- "Fit all fields" button to reset the view

## Dependencies

- `geopandas` — already in the data-pipeline venv
- `leaflet@1.9.4` — loaded from CDN at runtime in the browser (no pip install needed)

## Local validation

Run the script and verify that:

1. An HTML file appears for each grower
2. Each file opens in a browser and shows field polygons on a map
3. Clicking a field shows the popup with metadata
4. Clicking a field name in the sidebar zooms to that field
