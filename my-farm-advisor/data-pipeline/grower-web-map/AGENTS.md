# Grower Web Map Local Instructions

## Purpose

This subskill owns the grower-level interactive web map generator.
It reads published field-boundary GeoJSONs from the runtime data tree
and writes a self-contained Leaflet HTML page for each grower.

## Safe edit scope

Edits should stay inside this folder and its children.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` must be set to the runtime root.
- Reads `growers/<slug>/farms/<farm>/boundary/field_boundaries.geojson`.
- Writes `growers/<slug>/farm-web-map.html`.
- Uses the same runtime venv as the parent data-pipeline.

## Commands

Generate maps for all growers:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py
```

Generate map for one grower:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/generate_grower_map.py --grower-slug il-grower
```

## Output location

Output is a single HTML file per grower:

```
growers/<grower-slug>/farm-web-map.html
```

The map uses Leaflet from CDN; an internet connection is required to load
the basemap tiles.
