# Grower Web Map Subskill

Generates a lightweight, self-contained interactive HTML web map for each
existing grower. The map displays field polygon boundaries from the pipeline
output on an OpenStreetMap basemap, with click-to-inspect metadata and a
zoom-to-field sidebar.

## Usage

Run from the runtime source copy after the data pipeline has created at least
one grower with one or more farms and fields.

```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_web_map.py --grower-slug <grower-slug>
```

Use `--grower-slug all` to generate maps for every grower in the runtime tree.

## Output

- File: `growers/<grower>/derived/reports/grower_web_map.html`
- Self-contained HTML (Leaflet CDN, inline GeoJSON, no server required)

## Requirements

- Existing grower with at least one farm and field boundaries (from pipeline
  `download_fields.py` step)
- `DATA_PIPELINE_DATA_ROOT` set to the runtime root
- Internet access for Leaflet CSS/JS and OpenStreetMap tile loading

## Safe edit scope

Edits should stay in this directory (`grower-web-map/`) and the corresponding
script at `data-pipeline/src/scripts/generate_grower_web_map.py`. Do not
modify sibling subskill files, the parent `AGENTS.md`, or root policy unless
the change affects the shared library paths or runtime contract.
