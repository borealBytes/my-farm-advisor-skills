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

That command installs the runtime source and venv, builds shared geoadmin L0/L1/L2 payloads, shared NASA POWER county weather, GDD, annual corn RM, annual soybean MG, five-year FIPS-average corn RM and soybean MG datasets, and last-five-year CONUS CDL rasters. It then selects a top-crop county in the requested state, samples the requested number of OSM fields, and runs the full farm pipeline so derived tables, field weather, real DEM terrain, soil outputs, CDL history, satellite/NDVI products, reports, cards, posters, and HTML/Markdown farm reports are generated automatically. The generated farm and field reports do not integrate terrain metrics in this change.

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

## Default DEM terrain package

Normal farm pipeline initialization and add-field runs that invoke `scripts/run_farm_pipeline.py` include real DEM terrain by default. The pipeline calls `scripts/ingest/download_dem_terrain.py` immediately after field boundary download, passes live real-source permission through `--allow-live-downloads`, and writes elevation, slope, aspect, hillshade, curvature, wetness, depression, relative elevation, and erosion-proxy products under the runtime field tree. Generated farm and field reports do not integrate terrain metrics in this change.

Use `--skip-dem-terrain` only as an explicit operator override when a run must omit DEM terrain. The `scripts/run_farm_pipeline.py --structure-test` path remains a no-DEM, no-download structure check and must not import DEM-only dependencies or contact live services.

The direct DEM CLI remains available from the runtime source copy for focused dry runs, package inspection, or operator-led terrain retries. Direct CLI dry-run mode plans field paths and sources only. It does not write rasters, download DEM tiles, or require live provider services.

Safe temp-root install and dry-run check. This creates the runtime venv before invoking `.venv/bin/python`:

```bash
tmp_root="$(mktemp -d)"
export DATA_PIPELINE_DATA_ROOT="$tmp_root"
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_dem_terrain.py \
  --grower il-dekalb-grower \
  --farm dekalb-demo-farm \
  --context-meters 20 \
  --dry-run
```

For a no-network full-package smoke, use offline fixtures only as a direct CLI test-only synthetic path. These packages are not real grower DEM evidence, are not valid farm validation, and are marked with `synthetic_fixture=true`, `synthetic://...` source URLs, and warnings in the manifest/source reference. Synthetic fixture mode is unreachable from default farm-pipeline orchestration because `run_farm_pipeline.py` does not expose fixture flags. The CLI refuses fixture writes unless the deliberately named `--allow-synthetic-fixtures` test override is present. Prefer a temporary or disposable runtime root for this smoke:

```bash
tmp_root="$(mktemp -d)"
export DATA_PIPELINE_DATA_ROOT="$tmp_root"
cd my-farm-advisor/data-pipeline
./scripts/install.sh --non-interactive --force-refresh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_dem_terrain.py \
  --grower il-dekalb-grower \
  --farm dekalb-demo-farm \
  --context-meters 20 \
  --offline-fixtures \
  --allow-synthetic-fixtures \
  --limit-fields 1
```

Focused direct CLI runs for real grower DEM verification must use cached real source DEM rasters or live provider access. Live DEM provider discovery or downloads are disabled in direct CLI runs unless you opt in. Add `--allow-live-downloads` only when the operator expects network access, provider availability, and downloaded DEM cache writes under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/dem/`:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/download_dem_terrain.py \
  --grower il-dekalb-grower \
  --farm dekalb-demo-farm \
  --context-meters 20 \
  --allow-live-downloads
```

Default farm orchestration already invokes real DEM terrain with live real-source controls after field boundaries. Use `--dem-context-meters` and `--dem-source-policy` to tune that default path, or `--skip-dem-terrain` when the operator explicitly chooses to omit DEM terrain for a run.

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

## Grower Field Weather Dashboard

The data pipeline can generate a self-contained, single-file HTML weather
dashboard for any farm with field boundaries and weather data.  The dashboard
uses embedded Plotly.js for interactive charts, inlines all data, and has
**zero runtime external dependencies** — no CDN, no API calls, no external
fonts or images.  It works when opened directly from disk via `file://`.

### What it produces

The dashboard contains:

- An interactive Plotly field map with field polygons, click-to-toggle field
  selection, and an optional satellite basemap (downloaded at build time).
- A **Growing Degree Days** chart showing cumulative GDD (base 10°C) with
  per-field frost-date markers.
- A **Rainfall** chart showing daily rainfall bars and cumulative rainfall
  lines, with dual Y axes.
- Multi-select field and year dropdowns with Select all / Clear all controls.
- Shared X-axis pan/zoom across both charts.
- A Reset view button that restores the default selection and map extent.

### Full-pipeline mode

Dashboard generation is an **opt-in** final pipeline stage.  Add
`--generate-dashboard` to `run_farm_pipeline.py` or to the `farm_dashboard.py
create`/`refresh` subcommands:

```bash
python scripts/run_farm_pipeline.py \
  --grower-slug iowa-grower \
  --farm-slug iowa-grower-iowa \
  --farm-name "Iowa Corn Farm" \
  --generate-dashboard
```

Or from the farm dashboard orchestrator:

```bash
python scripts/farm_dashboard.py create \
  --grower-slug iowa-grower \
  --state Iowa \
  --field-count 4 \
  --generate-dashboard
```

Dashboard generation is **not** enabled by default — you must pass
`--generate-dashboard` explicitly.

### Standalone mode

Generate a dashboard for an existing farm without rerunning data acquisition.
Three ways to specify the target:

**1. Explicit farm directory (preferred):**
```bash
python scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/my-farm-advisor-runtime/data-pipeline/growers/iowa-grower/farms/iowa-grower-iowa
```

**2. Growers root with auto-discovery:**
```bash
python scripts/reporting/generate_weather_dashboard.py \
  --growers-dir ~/my-farm-advisor-runtime/data-pipeline
```

**3. Environment variable:**
```bash
export DATA_PIPELINE_DATA_ROOT=~/my-farm-advisor-runtime
python scripts/reporting/generate_weather_dashboard.py
```

**4. Via the farm dashboard CLI:**
```bash
python scripts/farm_dashboard.py dashboard generate \
  --farm-dir ~/my-farm-advisor-runtime/data-pipeline/growers/iowa-grower/farms/iowa-grower-iowa
```

### Custom output path

By default the dashboard is written to
`<farm-dir>/<farm-slug>_dashboard.html`.  Use `--output` to override:

```bash
python scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/path/to/farm \
  --output ~/custom/dashboard.html
```

### Skipping the basemap

If you are offline or want to skip the satellite basemap, use `--no-basemap`:

```bash
python scripts/reporting/generate_weather_dashboard.py \
  --farm-dir ~/path/to/farm \
  --no-basemap
```

The dashboard will still be fully functional with a neutral map background.

### Output location

Default output follows the project's canonical directory convention:

```
<farm-dir>/<farm-slug>_dashboard.html
```

For the Iowa fixture the default output is:
```
~/my-farm-advisor-runtime/data-pipeline/growers/iowa-grower/farms/iowa-grower-iowa/iowa-grower-iowa_dashboard.html
```

### Input data requirements

The dashboard generator reads from an existing farm output directory and does
**not** call any upstream data acquisition or processing stages.  Required
inputs:

- `boundary/field_boundaries.geojson` — FeatureCollection with field polygons
  in WGS84 (EPSG:4326).  Each feature should have `field_id` in properties.
  `area_acres` is read from feature properties when available.
- `farm.json` — Farm metadata with `farm_slug` and `display_name`.
- `fields/<field-slug>/field.json` — Per-field metadata (optional; falls back
  to the field slug).
- `fields/<field-slug>/weather/daily_weather.csv` — Per-field daily weather
  (optional; header-only or missing CSVs produce `(no data)` labels).
- `derived/tables/<farm>_weather_*.csv` — Farm-level aggregate weather table
  (used only as a fallback when no per-field weather is available).

### Weather calculations

For each field-year combination with weather data:

- **Last frost date**: The latest day before July 1 where `T2M_MIN ≤ 0°C`.
  Defaults to January 1 if no qualifying frost is found.
- **Daily GDD**: `max((T2M_MAX + T2M_MIN) / 2 - 10.0, 0)`.
- **Cumulative GDD**: Running total starting from the last frost date.
- **Daily rainfall**: `PRECTOTCORR × 0.0393701` (mm to inches).
- **Cumulative rainfall**: Running total starting from the last frost date.

All dates are sorted chronologically.  Missing `T2M_MIN`, `T2M_MAX`, or
`PRECTOTCORR` values cause that day to contribute zero to the relevant
cumulative total.

### Offline / runtime dependency guarantee

The generated HTML has **zero runtime external dependencies**:

- Plotly.js v2.x is downloaded at build time from the CDN and cached locally
  under `shared/reference/plotly/plotly-2.35.2.min.js`.  The cached bundle is
  inlined into the final HTML.
- No CDN references, API calls, externally loaded fonts, or external images
  appear in the output.
- The satellite basemap image (if requested) is downloaded and inlined as a
  base64 PNG at build time.
- The dashboard works from `file://` without a local web server.

### Troubleshooting

| Problem | Likely cause | Solution |
|---------|-------------|----------|
| `No farm directory discovered` | No valid farm found under search paths | Use `--farm-dir` to specify the path explicitly |
| `Multiple farm directories found` | More than one valid farm discovered | Use `--farm-dir` to select one |
| `Missing required boundary/field_boundaries.geojson` | Incomplete farm directory | Run field boundary download first |
| `No data for selected fields and years` | Empty or missing weather CSV | Run `download_weather.py` first, or check that the CSV has data rows |
| Basemap tiles not downloaded | Network issue or `--no-basemap` flag | Check connectivity; use `--no-basemap` for an offline-capable dashboard |
| Plotly download fails on first run | No internet at build time | Pre-download the bundle; the generator caches it for reuse |
