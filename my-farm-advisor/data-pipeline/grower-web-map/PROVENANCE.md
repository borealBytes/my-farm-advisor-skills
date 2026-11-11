# Grower Web Map Provenance

This file records data lineage, external services, licenses, and runtime policy for the `grower-web-map` subskill. It is a documentation record only. No downloaded or generated assets belong in this repository.

## Field boundary lineage

- Source of truth: the installed data pipeline's runtime artifacts under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`.
- Primary file: `farms/<farm>/boundary/field_boundaries.geojson`, written by the pipeline's boundary ingest.
- US fields in this catalog normally come from USDA NASS Crop Sequence Boundaries (CSB), distributed through the FIBOA `us-usda-cropland` GeoParquet collection (`https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet`). The FIBOA collection is CC-BY-4.0; the underlying CSB data is USDA public data.
- Non-US fields may come from OpenStreetMap (`landuse=farmland`) per `data-pipeline/references/field-boundary-sources.md`; OSM data is ODbL.
- The map preserves each feature's `source` property and shows it in the popup. It does not reinterpret or re-license the boundaries.
- The map does not embed imagery, GeoTIFFs, or report bundles. It embeds boundary coordinates, SSURGO polygon coordinates, and small clipped NDVI PNGs rendered at build time.

## Soil lineage

- Source: `farms/<farm>/fields/<field>/soil/ssurgo_soil_types.geojson` (map-unit polygons with `mukey`) and `ssurgo_full.csv` (component and surface-horizon attributes), written by the pipeline's soil download step.
- Origin: USDA NRCS Soil Survey Geographic Database (SSURGO), USDA public domain data.
- The map preserves `mukey` and shows it in both the legend and the popup; it does not re-derive or re-interpret soil properties.

## NDVI lineage

- Source: `farms/<farm>/fields/<field>/derived/features/ndvi_year_<year>_composite.tif`, written by the pipeline's NDVI step from Sentinel-2 imagery.
- The map renders each composite to a small PNG and clips it to the field boundary; the source GeoTIFF is never embedded.
- The colour scale (`-0.2`–`1.0`, matplotlib `RdYlGn`) is copied from the farm report's NDVI cards so values agree across artifacts.
- Sentinel-2 imagery attribution belongs to the pipeline's NDVI step and the farm report.

## Basemap

- Esri World Imagery:
  `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
- The skill does not cache, download, or redistribute tiles. The browser requests them directly at view time.
- Required attribution text is rendered by the Leaflet layer and must remain visible: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community".
- Esri terms of use apply to tile access: `https://www.esri.com/en-us/legal/terms/full-master-agreement`.

## Optional streets layer

- OpenStreetMap standard tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
- License: ODbL 1.0 (`https://www.openstreetmap.org/copyright`). Attribution must remain visible.
- The OpenStreetMap tile usage policy applies; this skill is for interactive human viewing, not bulk tile harvesting.

## Mapping library

- Leaflet 1.9.4, loaded from `https://unpkg.com/leaflet@1.9.4/`.
- License: BSD-2-Clause (`https://github.com/Leaflet/Leaflet/blob/main/LICENSE`).

## Runtime policy

- Generated maps live only under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/dashboards/`.
- Generated HTML must never be committed to Git, attached to provenance records, or treated as a source asset.
- The subskill itself contains code and documentation only.
- Python dependencies: standard library for boundaries and soils. The NDVI overlay uses `numpy`, `rasterio`, and `Pillow`, which the pipeline runtime venv already provides; without them the map still builds, with the NDVI layer skipped and one warning printed.

## Network policy

The map requires internet access at view time for Leaflet, Esri tiles, and optional OpenStreetMap tiles. No account, API key, or token is used. Offline viewing shows field outlines, soil fills, and NDVI overlays on a blank background.
