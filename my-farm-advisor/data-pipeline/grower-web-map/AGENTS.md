# Grower Web-Map Local Instructions

## Purpose

This subskill generates a self-contained interactive HTML web map for each grower in the data-pipeline runtime. It reads the downloaded field polygon boundaries from the pipeline output and produces a single Leaflet-based HTML map per grower.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader change. Do not change parent `AGENTS.md`, sibling workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. Review the main `data-pipeline/README.md` and `data-pipeline/AGENTS.md` for runtime conventions. Review `admin/interactive-web-map/GUIDE.md` for the general interactive-web-map workflow this subskill builds on.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` must be set as documented in `../AGENTS.md`.
- The script runs from the runtime source copy: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`.
- Generated maps are written to `growers/<grower>/derived/maps/grower_map.html`.
- The script uses `paths.py` (`lib/paths.py`) for path resolution.

## Command runbook

Generate maps for all growers:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py
```

Generate a map for a single grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py \
  --grower-slug illinois-grower
```

View the map by opening the output HTML in any web browser:

```bash
open "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/illinois-grower/derived/maps/grower_map.html"
```

## Map output

The generated HTML map includes:
- Leaflet.js with satellite (ESRI World Imagery) and street map (OSM) basemaps with toggle
- Field polygon boundaries colored by farm
- Click popups showing grower, farm, field name, area, county
- Sidebar field list — clicking a field name zooms the map to it
- Map auto-fits to show all fields on load

## Local validation

Run the script against the runtime with both `--grower-slug` and without to verify single-grower and all-growers modes. Confirm the output HTML files exist and contain valid Leaflet markup.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../AGENTS.md`.
