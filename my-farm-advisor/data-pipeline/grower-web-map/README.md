# Grower Web Map

Generate lightweight, interactive Leaflet-based HTML maps for each grower in the data-pipeline runtime.

## What it does

- Discovers all growers under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`
- Reads actual field boundary GeoJSON produced by the pipeline
- Emits one self-contained HTML file per grower

## Output

```
growers/<grower-slug>/derived/reports/<grower-slug>_web_map.html
```

## Map features

- OpenStreetMap basemap (internet required)
- All field polygons rendered with actual downloaded boundaries
- Click a field to see popup metadata: grower, farm, field name, area (acres)
- Sidebar field list; click any field to zoom to it
- Subtle per-farm color variation when a grower has multiple farms
- Auto-fit map bounds to the grower's fields

## Run

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/web_maps/generate_grower_web_map.py
```

## Requirements

No extra dependencies beyond the data-pipeline virtualenv (standard library + json). Leaflet CSS/JS loads from CDN; basemap tiles load from the internet.
