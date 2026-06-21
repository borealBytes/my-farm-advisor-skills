# Grower Web Map Subskill

## Assignment 1 – Interactive Grower-Level Web Map

This subskill generates a lightweight, self-contained interactive HTML map for each grower in the My Farm Advisor data pipeline.

### Subskill directory

- **Subskill definition:** `grower-web-map/AGENTS.md`
- **Usage guide:** `grower-web-map/GUIDE.md`
- **Source script:** `src/scripts/reporting/generate_grower_web_map.py`
- **Path helpers:** `src/scripts/lib/paths.py` (`grower_maps_dir()`, `grower_web_map_path()`)

### What It Does

- Scans all farms under `growers/<grower>/farms/`
- Reads the actual downloaded field polygon boundaries (`boundary/field_boundaries.geojson`)
- Enriches each field with metadata from `grower.json`, `farm.json`, and per-field `field.json`
- Produces a single HTML file per grower with embedded GeoJSON and Leaflet.js

### Map Features

- **Dual basemaps:** Esri Satellite and OpenStreetMap (CDN, togglable)
- **Layer switcher** in sidebar: Boundaries, NDVI (mean NDVI choropleth), Soil OM%, Soil pH, Crop Type
- **Soil polygon overlay** — toggleable SSURGO map-unit boundaries on all fields
- **Choropleth coloring** with dynamic legend that updates per layer
- **All fields** displayed with per-layer coloring and orange hover highlight
- **Click a field** to see an enhanced popup with: Grower, Farm, Field, Area, County, NDVI stats (mean, scenes), dominant soil, OM, pH, AWS, CEC, drainage, erosion risk
- **Sidebar field list** — shows metric per field matching active layer (area, NDVI, OM%, pH) and zooms on click
- **Zoom and pan** enabled
- **Canvas rendering** for performance
- **Small file size** (~15–30 KB per grower, summary values only, no rasters)

### Usage

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
export DATA_PIPELINE_VENV_DIR="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv"
"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src/scripts/reporting/generate_grower_web_map.py" \
  --grower-slug <grower-slug>
```

### Output

```
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower-slug>/maps/grower_web_map.html
```

### Examples

```bash
"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug il-grower

"${DATA_PIPELINE_VENV_DIR}/bin/python" \
  scripts/reporting/generate_grower_web_map.py \
  --grower-slug ia-grower
```
