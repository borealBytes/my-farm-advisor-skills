# Grower Web Map — Local Instructions

## Purpose

Generate a lightweight interactive Leaflet HTML map for each grower in the
data-pipeline runtime. The map uses field boundary GeoJSON from the canonical
pipeline output.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` for usage, options, and examples. Read `../AGENTS.md` and
`../README.md` for data-pipeline runtime and output path conventions.

## Runtime contract

- Requires `DATA_PIPELINE_DATA_ROOT` set to the absolute runtime root.
- Reads field boundaries from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<slug>/farms/<slug>/boundary/field_boundaries.geojson`.
- Writes output to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<slug>/farms/<slug>/derived/dashboards/grower_web_map.html`.
- Runs from the runtime source copy `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`.

## Command runbook

Generate maps for all growers:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py
```

Generate a map for a single grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py \
  --grower-slug il-grower
```

Override the output path:

```bash
../.venv/bin/python scripts/grower-web-map/generate_grower_web_map.py \
  --grower-slug il-grower \
  --output custom_map.html
```

## Map behavior

- Basemap: OpenStreetMap with ESRI Satellite toggle (Layer Control)
- Fields styled with semi-transparent green fill and dark outline
- Click a field: popup with grower, farm, field ID, county, area (acres)
- Sidebar: field list with click-to-zoom buttons, summary stats
- Auto-fit to bounds of all fields on load

## Local validation

Run the script against the existing growers and verify the generated HTML
opens and displays field polygons correctly.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent
or root files. Do not duplicate root-wide asset, vendor, or validation policy
here except this pointer to `../../../AGENTS.md`.
