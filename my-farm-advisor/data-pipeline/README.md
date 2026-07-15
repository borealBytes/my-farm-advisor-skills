# Data Pipeline Runtime Setup

This subskill ships the scripts that build the data-pipeline reports and
posters. Each runtime host creates its own virtualenv inside the data tree on
first run; the scripts auto-bootstrap that environment before continuing.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/bootstrap_farm_from_county.py \
  --state-fips 17 \
  --county-name DeKalb \
  --count 5 \
  --seed 77 \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --farm-name "DeKalb Demo Farm" \
  --run-pipeline \
  --force
```

For a first run that also initializes shared data and seeds fields for a grower in a state, use the installer directly from the checkout:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh \
  --prepare-shared-data \
  --seed-grower-slug acme-grower \
  --seed-state Illinois \
  --seed-field-count 12 \
  --seed-farm-name "Acme Illinois Farm"
```

That command installs the runtime source and venv, builds shared geoadmin L0/L1/L2 payloads, shared NASA POWER county weather, GDD, annual corn RM, annual soybean MG, five-year FIPS-average corn RM and soybean MG datasets, and last-five-year CONUS CDL rasters. It then selects a top-crop county in the requested state, samples the requested number of OSM fields, and runs the full farm pipeline so derived tables, field weather, soil outputs, CDL history, satellite/NDVI products, reports, cards, posters, and HTML/Markdown farm reports are generated automatically.

If the runtime is already installed, run the equivalent from the runtime source copy:

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/farm_dashboard.py create \
  --prepare-shared-data \
  --grower-slug acme-grower \
  --state Illinois \
  --field-count 12 \
  --farm-name "Acme Illinois Farm"
```

`DATA_PIPELINE_DATA_ROOT` is required. Set it to an absolute writable path outside the skill checkout before running the installer or any pipeline entrypoint. There is no implicit fallback to a platform workspace path or to a checkout-local `data/` directory.

The installer creates and refreshes the runtime tree under:

- runtime base: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`
- runtime source copy: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`
- default runtime venv: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv`

Generated outputs, manifests, reports, logs, and downloaded payloads belong under the runtime base, for example `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers` and `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared`. The committed checkout remains the source for installer scripts and baseline `src/` files, but runtime execution happens from the copied source.

Farm weather now uses NASA POWER's public S3 Zarr stores by default at actual field centroids. The default farm weather controls are `--weather-backend zarr`, `--weather-start-year 2021`, `--weather-end-year 2025`, and `--weather-time-standard lst`. The output path and CSV schema stay compatible with existing reports:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/<farm>_weather_2021_2025.csv
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/weather/daily_weather.csv
```

Run or override those defaults from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --farm-name "DeKalb Demo Farm" \
  --weather-backend zarr \
  --weather-start-year 2021 \
  --weather-end-year 2025 \
  --weather-time-standard lst
```

Use `--weather-backend api` only when explicitly debugging the legacy NASA POWER point API path for small field sets.

Shared county weather for maturity-by-FIPS uses NASA POWER's public S3 Zarr stores by default instead of issuing one `power.larc.nasa.gov` point API request per county grid cell. This avoids API rate-limit failures for L2 geoadmin scopes while preserving the existing output path and schema:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/weather/nasa-power/<year>/daily_weather_by_fips.parquet
```

For the full shared lower48 baseline, initialize the runtime with multi-year county weather, GDD, corn RM, soybean MG, corn/soybean five-year FIPS averages, and CDL raster outputs. The default shared maturity range is 2021-2025 to match the farm weather and CDL helper defaults; CDL initialization fetches the last five available CONUS rasters by default:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

That install flag runs the equivalent of:

```bash
python scripts/run_maturity_years_by_fips.py \
  --start-year 2021 \
  --end-year 2025 \
  --coverage lower48 \
  --weather-backend zarr \
  --weather-time-standard lst
python scripts/ingest/download_cdl.py \
  --raster-only \
  --cdl-scope conus \
  --cdl-latest-year 2025 \
  --cdl-window-years 5
```

`--prepare-shared-maturity` remains available for weather/GDD/corn/soy maturity only, but it does not prepare CDL rasters.

The maturity runner writes annual files like `shared/corn_maturity/tables/rm_by_fips_2025.parquet` and final five-year average files like `shared/corn_maturity/tables/rm_by_fips_2021_2025_average.parquet` and `shared/soybean_maturity/tables/mg_by_fips_2021_2025_average.parquet`.

For a single annual refresh, run:

```bash
python scripts/run_maturity_by_fips.py \
  --year 2025 \
  --coverage lower48 \
  --weather-backend zarr \
  --weather-time-standard lst
```

Use `--weather-backend api` only when explicitly debugging the legacy NASA POWER point API path for county weather.

## Grower Field Weather Dashboard

The data-pipeline can generate a production-quality, offline, single-file weather dashboard for any grower/farm output directory. The dashboard is an interactive HTML file with embedded Plotly charts showing cumulative growing degree days and rainfall per field-year, plus a satellite-backed field map.

### Standalone generation

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/my-farm-advisor-runtime/data-pipeline/growers/<grower>/farms/<farm>
```

The standalone command reads only existing pipeline outputs (boundaries, field metadata, per-field weather CSVs). It does not invoke weather downloads, field-boundary downloads, or external data processing.

Auto-discover a single available farm (fails with a clear error if multiple are found):

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_weather_dashboard.py
```

Custom output path:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/path/to/farm \
  --output ~/path/to/output.html
```

Skip satellite basemap (produces a fully functional dashboard with a neutral map background):

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/path/to/farm \
  --no-basemap
```

### Full pipeline integration

Dashboard generation can run as an optional final stage after all pipeline steps:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug <grower> \
  --farm-slug <farm> \
  --generate-dashboard
```

Use `--no-dashboard-basemap` to skip satellite basemap in pipeline mode, or `--dashboard-output <path>` for a custom output location.

### Runtime directory discovery

The dashboard generator resolves the farm directory with the following precedence:

1. Explicit `--farm-dir <path>`
2. Explicit `--growers-dir <path>` (must contain exactly one farm)
3. `MY_FARM_ADVISOR_DATA_ROOT` or `DATA_PIPELINE_DATA_ROOT` environment variable
4. Automatic discovery under `~` looking for likely runtime roots

If multiple valid farm directories exist and none is explicitly selected, the generator fails with a clear error listing all candidates. Never silently selects an arbitrary grower or farm.

### Input data assumptions

The generator expects the canonical farm layout:

```text
<farm-dir>/
  boundary/
    field_boundaries.geojson     (Polygon/MultiPolygon, EPSG:4326)
  fields/
    <field-id>/
      field.json                 (optional; falls back to field ID)
      weather/
        daily_weather.csv        (columns: date, T2M_MIN, T2M_MAX, PRECTOTCORR)
```

- Polygon and MultiPolygon geometries are supported.
- Missing `field.json`, empty weather directories, and header-only CSVs are tolerated gracefully.
- Fields without weather data are labeled `(no data)` in the field selector.

### Weather calculations

- Growing degree days: `dailyGdd = max((T2M_MAX + T2M_MIN) / 2 - 10.0, 0)` (base 10 degrees C)
- Cumulative GDD starts on the last frost date (latest day before July 1 where T2M_MIN <= 0 degrees C; January 1 if no qualifying frost is found)
- Daily rainfall: `dailyRainfallIn = PRECTOTCORR * 0.0393701` (mm to inches)
- Cumulative rainfall starts on the last frost date

### Offline guarantee

The generated HTML has zero runtime external dependencies:
- No CDN references (Plotly.js is vendored and inlined at build time)
- No external API calls
- No externally loaded fonts, CSS, JS, images, or data files
- Works from `file://` without a local web server

The Plotly.js v2.x bundle is downloaded once and cached under `shared/dashboard_assets/` in the runtime tree.

### Satellite basemap

At generation time, satellite imagery tiles are optionally fetched from Esri World Imagery, stitched with Pillow, and base64-encoded into the HTML. If tile download fails or `--no-basemap` is given, the generator produces a fully functional dashboard with a neutral background.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| No farm found | Use `--farm-dir`, `--growers-dir`, or set `MY_FARM_ADVISOR_DATA_ROOT` |
| Multiple farms found | Use `--farm-dir` to select one explicitly |
| Missing GeoJSON | Ensure `boundary/field_boundaries.geojson` exists in the farm directory |
| Empty weather data | Fields without data are labeled `(no data)`; this is not an error |
| Tile download failure | Use `--no-basemap` for a functional offline dashboard |
| Missing Plotly bundle | Run once with network access to cache the Plotly.js bundle |

To persist the default data root for future login sessions, write the user environment file and still export the variable in the current shell before running commands:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d"
cat > "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf" <<'EOF'
DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
EOF
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
```

The `environment.d` file applies to future sessions only. It does not update an already-running shell.

## Running inside OpenClaw CLI

When invoking the pipeline from the control UI or `openclaw-cli`, you can still
activate the environment explicitly, but the entrypoints will install and re-exec
themselves if the runtime venv is missing.

```bash
bash -lc 'export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime && \
  cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src" && \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
    scripts/run_farm_pipeline.py --grower-slug ... --farm-slug ...'
```

This ensures every pipeline step (including geopandas/rasterio operations) uses
the shared environment that lives alongside the replicated scripts.

## Assignment 3 — Field-Year Weather & NDVI Dashboard

**Reusable workflow**: Align Sentinel-2 NDVI observations with daily weather for a selected field-year, compute derived metrics, detect seasonal events, and generate a reusable four-panel dashboard.

**Selected field-year**: `northern-illinois-grower / osm-1499474531 / 2025`, crop **Soybeans**. Change the grower, field, and year constants at the top of each script to reuse the workflow for other supported field-years.

**Input files** (under the field's runtime directory):
- `weather/daily_weather.csv` — NASA POWER daily data at field centroid
- `satellite/sentinel/2025/*/sentinel_*_ndvi.tif` — per-date Sentinel-2 NDVI rasters
- `derived/tables/ndvi_year_crop_join.csv` — CDL crop classification

**Metrics calculated**: daily precipitation (`PRECTOTCORR`), average temperature (`T2M`), temperature extremes (`T2M_MAX`, `T2M_MIN`), and cumulative soybean GDD (base 10°C).

**Dashboard output** (relative to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`):
```
growers/northern-illinois-grower/farms/northern-illinois-grower-illinois/
  fields/osm-1499474531/derived/reports/assignment3_dashboard_2025.png
```

**To rerun**:
```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/assignment3_alignment.py
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/assignment3_dashboard.py
```

Step 5 (`assignment3_alignment.py`) produces `assignment3_aligned_data.csv` and `assignment3_events.json`. Step 6 (`assignment3_dashboard.py`) reads those outputs and renders the dashboard.

**Known limitations**:
- NDVI is plotted only at real Sentinel-2 acquisition dates (9 scenes for 2025); no daily interpolation is applied.
- Weather is daily NASA POWER point data at the field centroid, not spatially distributed.
- Annotations describe observed timing (e.g. "followed," "occurred near") and do not imply weather→NDVI causation.
- Soybean growth stages are estimated from cumulative GDD using literature-based thresholds; they are not field-verified.
