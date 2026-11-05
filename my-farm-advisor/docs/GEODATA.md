# Geoadmin Runtime Data

The geoadmin GeoJSON and Parquet payloads are **runtime data**, not repository content. This repo keeps the downloader code plus per-layer metadata, then rebuilds the payloads into the writable runtime tree when needed.

## Why the payloads are excluded from git

- `countries.geojson`, `states_usa.geojson`, and the related Parquet outputs are generated artifacts.
- They are rebuilt from the recorded upstream URLs, so committing them would duplicate large runtime payloads and make imports noisier.
- The committed source of truth is the metadata JSON plus the downloader implementation, not the downloaded GeoJSON payload itself.

## Metadata files and what they do

The committed metadata lives under `my-farm-advisor/data-pipeline/src/shared/geoadmin/`:

- `l0_countries/metadata.json` — Natural Earth countries source URL, archive name, and expected runtime output paths.
- `l1_states/metadata.json` — Census TIGER/Line states source URL, archive name, and expected runtime output paths.
- `l2_counties/metadata.json` — Census TIGER/Line counties source URL, archive name, expected runtime output paths, plus the county lookup parquet path.

Those metadata files currently resolve to these upstream archives:

- `l0_countries` → `https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip`
- `l1_states` → `https://www2.census.gov/geo/tiger/TIGER2025/STATE/tl_2025_us_state.zip`
- `l2_counties` → `https://www2.census.gov/geo/tiger/TIGER2025/COUNTY/tl_2025_us_county.zip`

Required metadata fields for each layer are:

- `source_url`
- `archive_name`
- `output_geojson`
- `output_parquet`

## Runtime destination

The downloader runs from the copied runtime source and writes the standardized payloads into the canonical runtime tree at:

- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l0_countries/`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l1_states/`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l2_counties/`

Expected outputs are:

- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l0_countries/countries.geojson`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l0_countries/countries.parquet`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l1_states/states_usa.geojson`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l1_states/states_usa.parquet`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l2_counties/counties_usa.geojson`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l2_counties/counties_usa.parquet`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/geoadmin/l2_counties/fips_lookup.parquet`

## Small-footprint site maps (client dashboards, trial footprints)

Any map that plots a few points on a basemap (BMS / BreedBase / IoT client examples) should
say where those points are in admin terms. `data-pipeline/src/scripts/lib/geoadmin_context.py`
adds it from the same cached layers — no new downloads:

```python
from geoadmin_context import add_admin_context
add_admin_context(ax, sites_gdf_3857, crs="EPSG:3857")
```

It clips to the axes view and draws L2 boundaries plus the full county / census-division name
of every unit touching the sites (nudged off markers), L1 boundaries plus a label per visible
state/province, and L0 country boundaries — white-on-imagery, deliberately subtle. The module
lifts `OGR_GEOJSON_MAX_OBJ_SIZE` **before** importing geopandas: pyogrio captures GDAL config
at import, so reordering that silently breaks the big country/Canada files.

## How to run the downloader

For the default first-run shared-data setup, use the data-pipeline installer. This builds geoadmin L0/L1/L2 before the shared weather and maturity steps:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

Set an explicit absolute runtime root, install the runtime copy, then run from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_geoadmin.py --levels l0_countries l1_states l2_counties --census-year 2025
```

Useful variants:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_geoadmin.py --list-sources
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_geoadmin.py --levels l2_counties --force
```

The script resolves the upstream download URLs from the committed metadata/catalog and performs the downloads itself. No manual asset download step is required.
