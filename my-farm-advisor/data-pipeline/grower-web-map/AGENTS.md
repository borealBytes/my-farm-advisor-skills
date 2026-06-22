# Local Instructions

## Purpose

This folder owns the **Assignment 1 grower-level interactive web-map** subskill.
It generates a lightweight, standalone HTML map for each grower from the
pipeline-produced field boundary GeoJSON.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `README.md` first for the quick-start and invocation examples. Review the
runtime `data-pipeline/AGENTS.md` for the runtime contract and environment
variables.

## Command runbook

### Generate a grower web map

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug <grower> \
  --farm-slug <farm>
```

### Example for Illinois grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm
```

Output:
```text
growers/northern-illinois-grower/farms/illinois-farm/derived/dashboards/illinois-farm_grower_webmap.html
```

### Example for Iowa grower

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug northern-iowa-grower \
  --farm-slug iowa-farm
```

Output:
```text
growers/northern-iowa-grower/farms/iowa-farm/derived/dashboards/iowa-farm_grower_webmap.html
```

## Runtime contract

- The script reads `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`
  from the runtime tree.
- It writes the HTML output to
  `growers/<grower>/farms/<farm>/derived/dashboards/<farm>_grower_webmap.html`.
- The generated HTML is self-contained: it embeds the GeoJSON inline and loads
  Leaflet.js and the basemap tiles from the internet. No server or external
  data files are required at runtime.
- Accepts `AG_GROWER_SLUG` and `AG_FARM_SLUG` environment variables as defaults.

## Map features

- Generic OpenStreetMap basemap (internet required for tiles).
- All field polygons for the grower rendered as interactive shapes.
- Click any field to see a popup with:
  - Grower name
  - Farm name
  - Field ID
  - Area (acres)
  - Crop name
- Sidebar panel lists every field with:
  - Field ID
  - Area (acres)
  - Crop name
  - A "Zoom" button that pans and zooms to the field and opens its popup.
- Standard zoom and pan controls.
- Map automatically fits to show all fields on load.
- Responsive layout adapts to mobile screens.

## Local validation

After creating or editing the script, copy it into the runtime source tree and
run a smoke test against an existing grower:

```bash
cd ~/my-farm-advisor-skills/my-farm-advisor/data-pipeline
cp src/scripts/reporting/generate_grower_webmap.py \
   ~/my-farm-advisor-runtime/data-pipeline/src/scripts/reporting/
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
cd ~/my-farm-advisor-runtime/data-pipeline/src
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm
```

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files. Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../AGENTS.md`.
