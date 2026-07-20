# Grower Web Map Subskill

## Purpose

This subskill generates a lightweight, self-contained interactive HTML web map for each grower in the My Farm Advisor data pipeline. Maps are generated from actual downloaded field polygon boundaries and enriched with grower/farm/field metadata.

## Files

- **Source script:** `../src/scripts/reporting/generate_grower_web_map.py`
- **Path helpers:** `../src/scripts/lib/paths.py` (provides `grower_maps_dir()`, `grower_web_map_path()`)
- **This file:** `grower-web-map/AGENTS.md`
- **Usage guide:** `grower-web-map/GUIDE.md`

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` must be set to the runtime root (outside the skill checkout).
- The script runs from the runtime source copy at `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`.
- Generated HTML maps are written to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower-slug>/maps/grower_web_map.html`.
- All map features (Leaflet.js, basemap tiles) load from public CDNs at runtime; no dependencies are bundled.

## Workflow

1. Edit `generate_grower_web_map.py` in the checkout `src/scripts/reporting/`.
2. Sync to runtime: `./scripts/install.sh --force-refresh --no-install-deps`.
3. Run: `"${RUNTIME_VENV}/bin/python" scripts/reporting/generate_grower_web_map.py --grower-slug <slug>`.

## Safe edit scope

Edit `generate_grower_web_map.py` and `paths.py` to change map behavior, styling, metadata enrichment, or output paths. Keep generated HTML output lightweight (no embedded rasters or satellite imagery).

## Layers

| Layer | Source | Description |
|-------|--------|-------------|
| NDVI | Latest yearly composite TIF via rasterio | Mean NDVI choropleth (green→red) |
| Soil OM% | `ssurgo_summary.csv` | Organic matter % choropleth (dark→light brown) |
| Soil pH | `ssurgo_summary.csv` | pH choropleth (optimal→extreme) |
| Crop Type | CDL composition CSV (if available) | Categorical colors (placeholder when unavailable) |
| Soil Polygons (overlay) | `ssurgo_soil_types.geojson` | SSURGO map-unit boundaries, toggleable checkbox |

## Validation

After editing, sync and generate a map for a known grower:
```bash
"${RUNTIME_VENV}/bin/python" scripts/reporting/generate_grower_web_map.py --grower-slug il-grower
```
Confirm the output HTML is < 50 KB, switches between all layers correctly, shows NDVI/soil data in popups, and toggles soil polygon overlay.
