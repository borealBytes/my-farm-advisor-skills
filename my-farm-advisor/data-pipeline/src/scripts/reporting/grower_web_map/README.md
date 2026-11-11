# Grower Web Map

A lightweight interactive web-map subskill for the My Farm Advisor data pipeline.

## Purpose

Generates a standalone HTML Leaflet map for each grower farm using the actual field boundary GeoJSON produced by the pipeline. The map displays field polygons on a CartoDB Positron basemap, supports zoom/pan, click popups with field metadata, and a sidebar field list for quick navigation.

## Dependencies

- `folium` (not bundled with the default pipeline venv; install separately)

## Usage

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/grower_web_map/generate_grower_web_map.py \
  --grower-slug <grower> \
  --farm-slug <farm> \
  --farm-name "Display Name"
```

## Output

```
growers/<grower>/farms/<farm>/derived/reports/<prefix>_grower_web_map.html
```

Open the HTML file in any modern web browser. No server is required.
