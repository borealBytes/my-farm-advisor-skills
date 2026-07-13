# Grower Web Map — Local Instructions

## Purpose

Generate self-contained interactive HTML web maps from real data-pipeline field boundaries. Use this when the user wants to visualize a grower's fields in a browser-based map with popups, legends, and basemap toggles.

## Safe edit scope

Edits should stay in this folder and its children. Do not change parent `SKILL.md`, sibling workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `INDEX.md` first, then review `scripts/generate_map.py` before changing map behavior.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required and must point to the runtime root that contains the `growers/` directory.
- The script reads `farm_boundaries.geojson`, `field-inventory.csv`, and per-field `field.json` from the runtime tree.
- The output HTML map is saved to the farm's `derived/reports/` directory under the runtime root.

## Command runbook

Generate a map for the Illinois grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
python scripts/generate_map.py --grower-slug il-grower
```

Generate a map for the Iowa grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
python scripts/generate_map.py --grower-slug ia-grower
```

Specify a farm slug explicitly:

```bash
python scripts/generate_map.py --grower-slug il-grower --farm-slug il-grower-illinois
```

## Output

The generated HTML file is a self-contained Leaflet.js map:

- All field boundaries rendered as colored polygons
- Field display name, area (acres), and field ID in popups
- OpenStreetMap and satellite basemap layer toggle
- Legend with field list
- Zoom-to-bounds on load

## Local validation

After changing the script, test against a known grower:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
python scripts/generate_map.py --grower-slug il-grower
```

Then open the output HTML in a browser.
