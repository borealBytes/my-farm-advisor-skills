# Data Pipeline Local Instructions

## Purpose

This folder owns the deterministic data-pipeline subskill. It copies committed baseline `src/` files into live runtime storage, then runs farm data, reporting, and poster scripts from that runtime copy.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `README.md` first. Review `scripts/install.sh`, `src/scripts/bootstrap_runtime.py`, and `src/scripts/run_farm_pipeline.py` before changing runtime or pipeline behavior. Read `../data-sources/INDEX.md` for related rebuild and reporting workflows.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required and must be an absolute writable path outside the skill checkout.
- Runtime base is `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`.
- Runtime source is `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`; run pipeline scripts from that copy, not from the checkout `src/`.
- Runtime venv is `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv` unless `DATA_PIPELINE_VENV_DIR` points to another absolute venv path.
- Generated outputs, downloaded payloads, reports, logs, and manifests belong under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`, not in the skill checkout, and must stay out of Git.
- User-level persistence defaults to `${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf` with simple `KEY=VALUE` lines. This does not update already-running shells, so also export variables in the current shell before running commands.
- Non-interactive runs fail fast when required environment is missing. They must not fall back to `/data/workspace` or checkout-relative roots.
- Runtime source drift prompts in interactive runs. Non-interactive CI or smoke runs must use `--force-refresh` when replacing a divergent runtime source is intended.

## Command runbook

First-time interactive install with an explicit external data root:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh
```

First-time install plus shared-data initialization and state-based field seeding:

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

Use this pattern when the user asks to initialize the data-pipeline and seed X fields for a grower in a specified state. The seeded farm slug and farm name can be omitted; `farm_dashboard.py create` derives stable defaults from grower and state. Because this path runs the full farm pipeline after seeding boundaries, derived tables, field weather, soil outputs, CDL history, satellite/NDVI products, reports, cards, posters, and HTML/Markdown farm reports should generate automatically.

Current-shell export for an existing runtime:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
export DATA_PIPELINE_VENV_DIR="${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv"
```

Persist the default data root for future login sessions:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d"
cat > "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf" <<'EOF'
DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
EOF
```

Smoke install into a temporary external root without writing repo-local `data/`:

```bash
tmp_root="$(mktemp -d)"
DATA_PIPELINE_DATA_ROOT="$tmp_root" ./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

Run a structure test from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py --structure-test
```

Run the farm pipeline with default field-location NASA POWER weather. Farm weather samples NASA POWER S3 Zarr at each field centroid, writes the existing farm weather CSV schema, and stages per-field `weather/daily_weather.csv` files:

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

Initialize shared geoadmin, maturity, weather, and CDL assets without seeding a farm:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

The shared maturity initializer writes annual corn RM and soybean MG outputs plus final last-five-year FIPS-average datasets such as `shared/corn_maturity/tables/rm_by_fips_2021_2025_average.parquet` and `shared/soybean_maturity/tables/mg_by_fips_2021_2025_average.parquet`.

Runtime equivalent after install:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/init_shared_data.py \
  --start-year 2021 \
  --end-year 2025 \
  --coverage lower48 \
  --weather-backend zarr \
  --weather-time-standard lst \
  --cdl-scope conus \
  --cdl-latest-year 2025 \
  --cdl-window-years 5
```

Use the legacy NASA POWER point API only for small debugging pulls:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --weather-backend api \
  --force
```

Force-refresh runtime source for non-interactive CI or smoke tests:

```bash
tmp_root="$(mktemp -d)"
DATA_PIPELINE_DATA_ROOT="$tmp_root" \
  ./scripts/install.sh --non-interactive --force-refresh --no-install-deps
```

Generate an interactive grower-level web map with Leaflet showing all farm field boundaries, NDVI overlay, and SSURGO soil overlay:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/grower_web_map.py \
  --grower-slug il-grower
```

The map is written to `growers/<grower-slug>/dashboards/grower_web_map.html`. Toggle between Boundaries, NDVI (peak 95th %ile), and SSURGO (selectable property) layers. Click any field to see grower, farm, area, county, and per-year crop composition from CDL history.

Root repository validation after documentation or structure changes:

```bash
cd ../..
./scripts/validate.sh
```

## Local workflow notes

- Keep this skill tiny and operational: copy baseline files from `src/` into live storage, preserve live data across reboot or redeploy, and use auditable `rsync` commands.
- Live data wins unless the user explicitly runs an upgrade or `--force-refresh` workflow.
- Safe data seeding uses `rsync -r --no-times --ignore-existing` and must not overwrite or delete existing files.
- Upgrade data seeding uses `rsync -r --no-times --checksum` and must not delete existing files.
- Keep `src/` shaped like the canonical runtime tree with `growers/`, `shared/`, and `scripts/`.
- Farm weather defaults are `AG_WEATHER_BACKEND=zarr`, `AG_WEATHER_START_YEAR=2021`, `AG_WEATHER_END_YEAR=2025`, and `AG_WEATHER_TIME_STANDARD=lst`. Use CLI arguments first, or set those environment variables for runtime scripts that do not accept CLI arguments directly.
- Do not commit `.env` files for data-pipeline defaults. Persist only `DATA_PIPELINE_DATA_ROOT` through the documented `environment.d` file; weather controls should remain explicit CLI arguments or current-shell exports.

## Local validation

For runtime setup changes, run a temp-root installer smoke command with `--non-interactive --force-refresh --no-install-deps` when dependencies are unavailable, then run `scripts/run_farm_pipeline.py --structure-test` from `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`. Otherwise run `./scripts/validate.sh` from the repository root after structural changes.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../AGENTS.md`.
