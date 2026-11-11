# Grower Web Map

Build a lightweight, self-contained interactive HTML map for each farm under an existing grower. The map reads the field polygons the data pipeline already downloaded, draws them over Esri World Imagery, and exposes basic metadata on click.

This package is import-safe and has no third-party Python dependencies. It does not download data, write shared caches, or modify farm artifacts other than the HTML map.

## What the map shows

- All fields of the farm, using `boundary/field_boundaries.geojson` (or per-field boundary files as a fallback).
- Esri World Imagery satellite basemap, with an OpenStreetMap streets layer and a layer switcher.
- Zoom, pan, scale bar, and "zoom to all fields".
- A sidebar field list; clicking a field flies to it and opens its popup.
- Click popups with grower, farm, field name/id, area (ac + ha), crop, county/state, and boundary source when present.

Output is a single HTML file with embedded polygon coordinates and attributes only. Imagery, rasters, and report bundles are never embedded.

## Prerequisites

- An installed data-pipeline runtime: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline` with existing growers.
- A browser with internet access for the Esri tiles, OpenStreetMap tiles, and the Leaflet CDN.
- Python 3.10+ (the runtime venv works; no extra packages are required).

## Seed into an existing runtime

Copy the subskill into the runtime so it runs beside the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
rsync -a --delete my-farm-advisor/data-pipeline/grower-web-map/ \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/"
```

Re-run the copy after editing the subskill. The data pipeline installer refreshes `data-pipeline/src`; this subskill lives beside it, so the explicit copy is the seeding step.

## Run

```bash
export DATA_PIPELINE_DATA_ROOT="$HOME/my-farm-advisor-runtime"
PYTHONPATH="$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/src" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" -m grower_web_map --all-growers
```

Single grower:

```bash
PYTHONPATH="$DATA_PIPELINE_DATA_ROOT/data-pipeline/grower-web-map/src" \
  "$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" -m grower_web_map \
  --grower-slug illinois-grower
```

The CLI also accepts `--data-root <path>` instead of the environment variable.

## Output contract

| Artifact | Location |
| --- | --- |
| Per-farm map | `growers/<grower>/farms/<farm>/derived/dashboards/<farm>_fields_map.html` |

- One map per farm. A grower with multiple farms gets one map per farm, and every field of the grower appears on its farm's map.
- The file is static HTML (`text/html`), typically 15-40 KB for a few fields.
- Existing dashboard files are not touched; only `<farm>_fields_map.html` is written or replaced.

## Data contract

Inputs are read relative to the runtime root:

```
growers/<grower>/grower.json
growers/<grower>/farms/<farm>/farm.json
growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson
growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson   # fallback
```

Recognized feature properties: `field_id`, `name`, `area_acres`, `area_ha_est`, `crop`, `county`, `state`, `source`. Missing properties are omitted from the popup instead of being invented. Coordinates are rounded to six decimal places to keep the file small.

If a farm has no boundary features, the CLI prints `skip` for that farm and continues. If no maps are written at all, it exits non-zero.

## Viewing

Open the HTML file directly in a browser, or serve the runtime root:

```bash
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline"
python3 -m http.server 8000
# then open http://localhost:8000/growers/<grower>/farms/<farm>/derived/dashboards/
```

Tiles and Leaflet load from the network. Without internet the page still shows field outlines on a blank background, but no satellite imagery.

## Attribution and licensing

- Field boundaries come from the data pipeline; keep the `source` property visible in popups. US boundaries are typically USDA NASS Crop Sequence Boundaries via FIBOA (CC-BY-4.0 collection, USDA public data).
- Esri World Imagery: keep the on-map Esri attribution text.
- OpenStreetMap tiles: ODbL, keep the OpenStreetMap attribution.
- Leaflet 1.9.4: BSD-2-Clause.

See [PROVENANCE.md](PROVENANCE.md) for the full record.

## Validation

- Generated HTML stays under `DATA_PIPELINE_DATA_ROOT` and is never committed.
- Repo checks: run `./scripts/validate.sh` from the repository root.
