# Grower Web Map Provenance

This file records data lineage, external services, licenses, and runtime policy for the `grower-web-map` subskill. It is a documentation record only. No downloaded or generated assets belong in this repository.

## Field boundary lineage

- Source of truth: the installed data pipeline's runtime artifacts under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/`.
- Primary file: `farms/<farm>/boundary/field_boundaries.geojson`, written by the pipeline's boundary ingest.
- US fields in this catalog normally come from USDA NASS Crop Sequence Boundaries (CSB), distributed through the FIBOA `us-usda-cropland` GeoParquet collection (`https://data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet`). The FIBOA collection is CC-BY-4.0; the underlying CSB data is USDA public data.
- Non-US fields may come from OpenStreetMap (`landuse=farmland`) per `data-pipeline/references/field-boundary-sources.md`; OSM data is ODbL.
- The map preserves each feature's `source` property and shows it in the popup. It does not reinterpret or re-license the boundaries.
- The map does not embed imagery, rasters, soil polygons, or report bundles. Only boundary coordinates and selected attributes are written into the HTML.

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
- Python dependencies: standard library only. No new packages are required beyond the data-pipeline runtime.

## Network policy

The map requires internet access at view time for Leaflet, Esri tiles, and optional OpenStreetMap tiles. No account, API key, or token is used. Offline viewing shows field outlines only.
