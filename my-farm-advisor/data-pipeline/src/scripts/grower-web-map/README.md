# Grower Web Map

Generates a lightweight interactive Leaflet HTML map for each grower,
displaying field polygon boundaries from the pipeline output with
clickable metadata popups and a field list sidebar.

## Usage

From the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/grower-web-map/generate_grower_web_map.py
```

Process a single grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/grower-web-map/generate_grower_web_map.py \
  --grower-slug il-grower
```

## Output

Maps are written to:
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/derived/dashboards/grower_web_map.html`

Each HTML file is self-contained (~80–120 KB) with embedded GeoJSON
and loads basemap tiles from OpenStreetMap. No additional dependencies
are needed; just open the file in a browser.
