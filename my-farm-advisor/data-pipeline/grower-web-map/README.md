# Grower Web Map

Build a lightweight, self-contained interactive HTML map for each farm under an existing grower. The map reads what the data pipeline already wrote — field polygons, SSURGO soil map units, and yearly NDVI composites — draws them over Esri World Imagery, and exposes basic metadata on click.

The package does not download data, write shared caches, or modify farm artifacts other than the HTML map. Building the soil layer needs only the standard library; the NDVI overlay additionally needs `numpy`, `rasterio`, and `Pillow`, and degrades gracefully (map builds, NDVI layer absent, one warning) when they are missing.

## What the map shows

- All fields of the farm, using `boundary/field_boundaries.geojson` (or per-field boundary files as a fallback).
- Esri World Imagery satellite basemap, with an OpenStreetMap streets layer and a layer switcher.
- Zoom, pan, scale bar, and "zoom to all fields".
- A sidebar field list; clicking a field flies to it and opens its popup.
- Click popups with grower, farm, field name/id, area (ac + ha), crop, county/state, and boundary source when present.

Three overlays, all toggled from the Leaflet layers control:

| Overlay | Default | Source | Interaction |
| --- | --- | --- | --- |
| SSURGO soils | off | `fields/<field>/soil/ssurgo_soil_types.geojson` | hover highlights the matching legend row, popup per map unit |
| NDVI | off | `fields/<field>/derived/features/ndvi_year_*_composite.tif` | year chips 2021–2025 switch the raster |
| Field boundaries | on | `boundary/field_boundaries.geojson` | click popup, hover highlight |

Overlay draw order is NDVI below soils below boundaries, so a field outline stays readable on top of either raster.

## Soil layer

One polygon per soil map unit per field, coloured from a categorical palette assigned in `mukey` order so a unit keeps its colour across rebuilds. Component name, drainage class, organic matter, pH, and available water capacity come from `ssurgo_full.csv` via the dominant component's surface horizon.

The sidebar legend groups rows by field, sorted by area, showing swatch, map-unit key (`mukey`), series name, drainage class, acres, and percent of field. Units under 0.05 ac are labelled `trace` and their share renders as `<1%`; per-field percentages include them and sum to 100.

## NDVI layer

Each year's composite is rendered to a palette PNG at build time and embedded as a data URI, clipped to the field boundary with `rasterio.features.rasterize`. The composites themselves are clipped to a padded box rather than the field, so roughly two-thirds of their valid pixels are neighbouring ground — the boundary clip is what keeps the overlay inside the field.

The colour scale is fixed at `-0.2` to `1.0` with matplotlib's `RdYlGn`, deliberately identical to the NDVI cards in the farm report, so a value has the same colour in both artifacts. Images are capped at 256 px on the long side; a per-year caption reports the crop and mean NDVI of the fields shown.

## Prerequisites

- An installed data-pipeline runtime: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline` with existing growers.
- A browser with internet access for the Esri tiles, OpenStreetMap tiles, and the Leaflet CDN.
- Python 3.10+ (the runtime venv works). `numpy`, `rasterio`, and `Pillow` are required only for the NDVI overlay; the runtime venv already has them.

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

The CLI also accepts `--data-root <path>` instead of the environment variable. Each farm prints one `map` line with its field, soil-polygon, and NDVI-year counts.

## Output contract

| Artifact | Location |
| --- | --- |
| Per-farm map | `growers/<grower>/farms/<farm>/derived/dashboards/<farm>_fields_map.html` |

- One map per farm. A grower with multiple farms gets one map per farm, and every field of the grower appears on its farm's map.
- The file is static HTML (`text/html`). Size is driven by the overlays: roughly 80–150 KB for a small farm, up to ~900 KB where fields are large and have many soil units or NDVI pixels.
- Existing dashboard files are not touched; only `<farm>_fields_map.html` is written or replaced.

## Data contract

Inputs are read relative to the runtime root:

```
growers/<grower>/grower.json
growers/<grower>/farms/<farm>/farm.json
growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson
growers/<grower>/farms/<farm>/manifests/field-inventory.csv                 # field_id -> field_slug
growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson # fallback
growers/<grower>/farms/<farm>/fields/<field>/soil/ssurgo_soil_types.geojson  # soil polygons (mukey)
growers/<grower>/farms/<farm>/fields/<field>/soil/ssurgo_full.csv            # component attributes
growers/<grower>/farms/<farm>/fields/<field>/derived/features/ndvi_year_<year>_composite.tif
growers/<grower>/farms/<farm>/fields/<field>/derived/summaries/ndvi_yearly_summary.json
```

Recognized feature properties: `field_id`, `name`, `area_acres`, `area_ha_est`, `crop`, `county`, `state`, `source`. Missing properties are omitted from the popup instead of being invented. Coordinates are rounded to six decimal places to keep the file small.

Soils and NDVI are optional per farm. A farm with no soil polygons simply omits the soil overlay and legend; a farm with no NDVI rasters (or a runtime without `rasterio`) omits the NDVI overlay. Each omission prints a `warn` line and does not fail the run. NDVI rasters that are not in WGS84 are skipped.

If a farm has no boundary features, the CLI prints `skip` for that farm and continues. If no maps are written at all, it exits non-zero.

## Viewing

Open the HTML file directly in a browser, or serve the runtime root:

```bash
cd "$DATA_PIPELINE_DATA_ROOT/data-pipeline"
python3 -m http.server 8000
# then open http://localhost:8000/growers/<grower>/farms/<farm>/derived/dashboards/
```

The HTML is self-contained, so `file://` works too. Tiles and Leaflet load from the network. Without internet the page still shows field outlines, soil fills, and NDVI overlays on a blank background, but no satellite imagery.

## Attribution and licensing

- Field boundaries come from the data pipeline; keep the `source` property visible in popups. US boundaries are typically USDA NASS Crop Sequence Boundaries via FIBOA (CC-BY-4.0 collection, USDA public data).
- SSURGO soils: USDA NRCS public domain data, delivered by the pipeline's soil download step.
- NDVI composites: derived by the pipeline from Sentinel-2 imagery; attribution belongs to the farm report.
- Esri World Imagery: keep the on-map Esri attribution text.
- OpenStreetMap tiles: ODbL, keep the OpenStreetMap attribution.
- Leaflet 1.9.4: BSD-2-Clause.

See [PROVENANCE.md](PROVENANCE.md) for the full record.

## Validation

- Generated HTML stays under `DATA_PIPELINE_DATA_ROOT` and is never committed.
- Repo checks: run `./scripts/validate.sh` from the repository root.
